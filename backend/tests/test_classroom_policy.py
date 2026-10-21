# SPDX-License-Identifier: AGPL-3.0-only
"""Prepared hermetic authority/private-state tests. No runtime acceptance implied."""

import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine

from app.auth import Identity, Membership, _grant_ref
from app.classroom import policy as teaching
from app.classroom.router import build_router
from app.classroom.store import NOTICE, PrivateStore, metadata
from app.config import settings
from app.controls.data import ExecutionData
from app.conversations.router import build_router as conversations
from tests.classroom_offline import deny_external  # noqa: F401
from tests.http_auth import configure, token

EX = teaching.EXERCISE
VERSION = "info511-lab3-q4-synthetic-v1"


@pytest.fixture
def classroom(monkeypatch, tmp_path):
    grants = json.loads(
        (Path(__file__).parent / "fixtures/classroom/authorization.example.json").read_text()
    )
    auth_file = configure(monkeypatch, tmp_path, grants)
    member = Membership(**grants["subjects"]["synthetic-one"][0])
    identity = Identity(
        member.institution_id,
        member.class_id,
        member.learner_id,
        tuple(member.assignments.items()),
        EX,
        VERSION,
        tuple(member.assignments.items()),
        _grant_ref("synthetic-one", member),
    )
    engine = create_engine("sqlite:///" + str(tmp_path / "private.db"))
    metadata.create_all(engine)
    clock = [1000.0]
    store = PrivateStore(engine, now=lambda: clock[0])
    monkeypatch.setattr(teaching, "configured_store", lambda: store)
    monkeypatch.setattr("app.classroom.router.configured_store", lambda: store)
    return identity, store, teaching.policy_for(identity), grants, auth_file, clock


def checkpoint(identity, store, policy):
    store.update(
        identity,
        policy,
        "checkpoint_00000001",
        "checkpoint",
        {"schema_present": True, "unit_present": True},
    )


@pytest.mark.parametrize(
    "payload", [{"stance": "oracle"}, {"stance": "control"}, {"mode": "teach"}]
)
def test_client_cannot_select_answer_mode(classroom, payload):
    identity, _, _, _, _, _ = classroom
    with pytest.raises(HTTPException) as denied:
        teaching.enforce(identity, payload, observe=True)
    assert denied.value.status_code == 403
    assert denied.value.detail["kind"] == "policy_guidance"


def test_checkpoint_not_research_consent_or_monitor_permission(classroom):
    identity, store, policy, _, _, _ = classroom
    with pytest.raises(HTTPException) as reminder:
        teaching.enforce(identity, {})
    assert reminder.value.detail["kind"] == "completion_reminder"
    checkpoint(identity, store, policy)
    teaching.enforce(identity, {})
    assert store.read(identity, policy)["monitor"] == "off"


def test_private_loop_pause_revoke_dedup_and_no_ai(classroom):
    identity, store, policy, _, _, clock = classroom
    checkpoint(identity, store, policy)
    store.update(identity, policy, "enable_0000000001", "enable", {"notice_version": NOTICE})
    observed = store.observe(
        identity, policy, "tool_denied", "hints_only", "policy_guidance", operation_id="attempt-one"
    )
    store.observe(
        identity, policy, "tool_denied", "hints_only", "policy_guidance", operation_id="attempt-one"
    )
    for action in ("guidance_opened", "challenge", "retry"):
        store.update(
            identity,
            policy,
            action + "_0000000000000001",
            action,
            {"alert_id": observed["alert_id"]},
        )
    assert len(store.read(identity, policy)["alerts"]) == 1
    store.update(identity, policy, "pause_00000000001", "pause")
    before = store.read(identity, policy)["events"]
    store.observe(identity, policy, "checker_result", "check_needs_attention", "learning_feedback")
    assert store.read(identity, policy)["events"] == before
    teaching.enforce(identity, {})
    store.update(identity, policy, "declare_00000001", "declaration", {"declaration": "no_ai"})
    state = store.update(identity, policy, "revoke_0000000001", "revoke")
    assert state["events"] == [] and state["alerts"] == {}
    assert state["checkpoint"] and state["declaration"] == "no_ai"
    assert store.read(replace(identity, learner_id="edu:2"), policy)["events"] == []
    clock[0] = state["expires_at"]
    assert store.read(identity, policy)["checkpoint"] is False
    with pytest.raises(HTTPException):
        teaching.enforce(identity, {})


def test_policy_and_membership_rechecked_before_each_provider_call(classroom):
    identity, store, policy, grants, auth_file, _ = classroom
    checkpoint(identity, store, policy)
    calls = []
    provider = teaching.guard_provider(
        identity, {}, SimpleNamespace(json=lambda **kw: calls.append(kw))
    )
    provider.json(role="planner")
    grants["subjects"]["synthetic-one"] = []
    auth_file.write_text(json.dumps(grants))
    with pytest.raises(HTTPException):
        provider.json(role="reasoner")
    assert len(calls) == 1


def test_missing_policy_cannot_enable_pilot_tutoring(classroom):
    identity, _, _, grants, auth_file, _ = classroom
    del grants["teaching_policies"]
    auth_file.write_text(json.dumps(grants))
    with pytest.raises(HTTPException) as unavailable:
        teaching.enforce(identity, {})
    assert unavailable.value.status_code == 503


def test_queue_submission_checks_before_touching_coordinator(classroom):
    identity, _, _, _, _, _ = classroom
    store = object.__new__(ExecutionData)
    with pytest.raises(HTTPException) as denied:
        store.submit(identity, "request_0000000001", {"stance": "oracle"}, "/api/sol/jobs")
    assert denied.value.status_code == 403


@pytest.mark.parametrize("prefix", ["/api", "/quad/v1"])
@pytest.mark.parametrize("controlled", [False, True])
@pytest.mark.parametrize("endpoint", ["turns", "jobs"])
def test_saved_route_cannot_inherit_client_oracle(
    classroom, monkeypatch, prefix, controlled, endpoint
):
    monkeypatch.setattr(
        settings, "controls_mode", "enforced" if controlled else "development_bypass"
    )
    monkeypatch.setattr(settings, "controls_jobs_enabled", False)
    fake = SimpleNamespace(
        get=lambda *a: {"exercise_id": EX, "exercise_version": VERSION},
        policy=SimpleNamespace(max_body_bytes=65536),
    )
    app = FastAPI()
    app.include_router(
        conversations(
            prefix,
            None,
            None,
            lambda: pytest.fail("provider constructed"),
            engine=classroom[1].engine,
            repository_factory=lambda: fake,
        )
    )
    client = TestClient(app)
    result = client.post(
        prefix + "/conversations/fake/" + endpoint,
        headers={"Authorization": "Bearer " + token("synthetic-one")},
        json={
            **(
                {"participant_id": "edu:1", "exercise_id": EX, "exercise_version": VERSION}
                if endpoint == "jobs"
                else {}
            ),
            "request_id": "saved_0001",
            "expected_revision": 0,
            "message": "Explain identifiers",
            "stance": "oracle",
        },
    )
    assert result.status_code == 403


@pytest.mark.parametrize("prefix", ["/api", "/quad/v1"])
@pytest.mark.parametrize("untrusted_field", ["prompt", "grade", "grade_write", "score"])
def test_private_http_closed_fields_and_isolation(classroom, prefix, untrusted_field):
    app = FastAPI()
    app.include_router(build_router(prefix))
    client = TestClient(app)
    path = prefix + "/classroom/" + EX + "/" + VERSION
    headers = {"Authorization": "Bearer " + token("synthetic-one")}
    assert client.get(path).status_code == 401
    assert (
        client.post(
            path,
            headers=headers,
            json={
                "expected_revision": 0,
                "action": "enable",
                "request_id": "request_000000001",
                "notice_version": NOTICE,
                untrusted_field: "not collected",
            },
        ).status_code
        == 422
    )
    response = client.post(
        path,
        headers=headers,
        json={
            "expected_revision": 0,
            "action": "enable",
            "request_id": "request_000000001",
            "notice_version": NOTICE,
        },
    )
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    other = client.get(path, headers={"Authorization": "Bearer " + token("synthetic-two")})
    assert other.json()["monitor"] == "off"


@pytest.mark.parametrize(
    "route", ["/api/sol/turn", "/quad/v1/turn", "/api/sol/jobs", "/quad/v1/jobs"]
)
def test_all_unsaved_http_paths_deny_oracle_before_execution(classroom, monkeypatch, route):
    from app.main import app

    monkeypatch.setattr(settings, "controls_mode", "development_bypass")
    client = TestClient(app)
    body = {"exercise_id": EX, "exercise_version": VERSION, "stance": "oracle"}
    if route == "/quad/v1/turn":
        body["pseudo_id"] = "edu:1"
    else:
        body["participant_id"] = "edu:1"
    if route.endswith("jobs"):
        body["request_id"] = "request_000000001"
    result = client.post(
        route, headers={"Authorization": "Bearer " + token("synthetic-one")}, json=body
    )
    assert result.status_code == 403
    assert result.json()["detail"]["code"] == "hints_only"


def test_delayed_enable_cannot_undo_revoke(classroom):
    identity, store, policy, _, _, _ = classroom
    enabled = store.update(
        identity,
        policy,
        "enable_0000000001",
        "enable",
        {"notice_version": NOTICE},
        expected_revision=0,
    )
    revoked = store.update(
        identity, policy, "revoke_0000000001", "revoke", expected_revision=enabled["revision"]
    )
    with pytest.raises(HTTPException) as conflict:
        store.update(
            identity,
            policy,
            "enable_0000000001",
            "enable",
            {"notice_version": NOTICE},
            expected_revision=0,
        )
    assert conflict.value.status_code == 409
    assert store.read(identity, policy)["revision"] == revoked["revision"]


def test_optional_tracking_error_cannot_change_required_denial(classroom, monkeypatch):
    identity, store, _, _, _, _ = classroom

    def fail(*args, **kwargs):
        raise HTTPException(503, "private store unavailable")

    monkeypatch.setattr(store, "update", fail)
    with pytest.raises(HTTPException) as denied:
        teaching.enforce(identity, {"stance": "oracle"}, observe=True)
    assert denied.value.status_code == 403
    assert denied.value.detail["monitor_state"] == "unavailable"


def test_actual_checker_errors_are_learning_feedback_without_policy_alert(classroom):
    identity, store, policy, _, _, _ = classroom
    store.update(identity, policy, "enable_0000000001", "enable", {"notice_version": NOTICE})
    teaching.record_check(identity, {"ok": True, "goalMet": False})
    state = store.read(identity, policy)
    assert state["alerts"] == {}
    assert state["events"][0]["kind"] == "learning_feedback"


def test_private_buffer_cannot_block_pause_or_required_checkpoint(classroom):
    from app.classroom.store import sessions

    identity, store, policy, _, _, _ = classroom
    enabled = store.update(
        identity, policy, "enable_0000000001", "enable", {"notice_version": NOTICE}
    )
    body = {k: v for k, v in enabled.items() if k not in {"expires_at", "revision"}}
    body["requests"] = {str(i): "digest" for i in range(128)}
    body["events"] = [{"action": "guidance_opened"} for _ in range(64)]
    with store.engine.begin() as conn:
        conn.execute(sessions.update().values(body=body))
    state = store.update(
        identity,
        policy,
        "checkpoint_full1",
        "checkpoint",
        {"schema_present": True, "unit_present": True},
    )
    assert state["checkpoint"] and len(state["requests"]) == 128
    paused = store.update(identity, policy, "pause_00000000001", "pause")
    assert paused["monitor"] == "paused"
    teaching.enforce(identity, {})


@pytest.mark.parametrize("retry", ["format", "reformat"])
@pytest.mark.parametrize("boundary", ["direct", "queued"])
@pytest.mark.parametrize("revocation", ["membership", "teaching_policy"])
def test_inner_retry_rechecks_actual_authority(
    classroom, monkeypatch, ledger, retry, boundary, revocation
):
    """Use the real provider retry and runtime ledger, with an in-memory SDK double."""
    from cryptography.fernet import Fernet
    from sqlalchemy import select

    from app.controls.contracts import Amount, ControlError
    from app.controls.jobs_worker import AskAdapter
    from app.controls.ledger import attempts
    from app.controls.runtime import operation
    from app.packs.datascience.pack import DataSciencePack
    from app.store import ConsentRouter, InMemoryStore
    from tests.test_controls_execution import funded, invoke, provider, response

    identity, store, policy, grants, auth_file, _ = classroom
    checkpoint(identity, store, policy)
    funded(ledger)
    monkeypatch.setattr(settings, "llm_billing_mode", "metered")
    monkeypatch.setattr(settings, "openai_response_format", "json_object")
    monkeypatch.setattr(settings, "controls_inference_expires_at", 0)
    execution = ExecutionData(ledger, "test", Fernet.generate_key())
    payload = {
        "exercise_id": EX,
        "exercise_version": VERSION,
        "participant_id": identity.learner_id,
        "stance": "peer",
        "mode": "study",
    }
    job = execution.submit(identity, "inner_retry_00001", payload, "/api/sol/jobs")
    with ledger.transaction() as conn:
        queue_before = dict(
            conn.execute(select(attempts).where(attempts.c.id == "queue:" + job["id"]))
            .mappings()
            .one()
        )
    assert queue_before["kind"] == "queue" and queue_before["state"] == "reserved"
    assert queue_before["actual"] is None
    assert queue_before["reserved"] == Amount().model_dump()
    claimed = execution.admission.claim()
    assert claimed["id"] == job["id"]
    value, calls = provider([])

    class FormatRejected(Exception):
        status_code = 400

    def first_attempt(**kwargs):
        calls.append(kwargs)
        if revocation == "membership":
            grants["subjects"]["synthetic-one"] = []
        else:
            grants["teaching_policies"] = {}
        auth_file.write_text(json.dumps(grants))
        if retry == "format":
            raise FormatRejected()
        return response("not JSON")

    value._client.chat.completions.create = first_attempt
    adapter = AskAdapter(
        execution, ConsentRouter(InMemoryStore()), DataSciencePack(), lambda: value
    )
    guard = (lambda: adapter.check(claimed)) if boundary == "queued" else None
    wrapped = value if boundary == "queued" else teaching.guard_provider(identity, payload, value)
    with operation(ledger, execution.scope(identity), job["id"], guard):
        with pytest.raises((HTTPException, ControlError)):
            invoke(wrapped)
    # Denial must happen before the internal format/reformat second SDK attempt.
    assert len(calls) == 1
    with ledger.transaction() as conn:
        rows = list(conn.execute(select(attempts)).mappings())
    # Queue admission is a separate retained accounting row, not a provider call.
    # claim() settles that queue hold; the provider attempt has its own liability.
    queue_rows = [row for row in rows if row["kind"] == "queue"]
    model_rows = [row for row in rows if row["kind"] == "model"]
    assert len(rows) == 2 and len(queue_rows) == len(model_rows) == 1
    queue, model = queue_rows[0], model_rows[0]
    assert queue["id"] == queue_before["id"] == "queue:" + job["id"]
    assert queue["reserved"] == queue_before["reserved"]
    assert queue["state"] == "settled" and queue["actual"] == Amount().model_dump()
    assert all(row["operation"] == job["id"] for row in rows)
    assert all(row["scopes"] == list(execution.scope(identity).keys()) for row in rows)
    assert model["reserved"]["tokens"] > 0 and model["reserved"]["microunits"] > 0
    summary = ledger.summary()
    if retry == "format":
        # A received format rejection proves the call ended, not its token usage.
        assert model["state"] == "unknown" and model["actual"] is None
        assert summary["reserved"] == model["reserved"]
        assert summary["consumed"] == Amount().model_dump()
    else:
        assert model["state"] == "settled"
        assert model["actual"] == Amount(tokens=15, microunits=20).model_dump()
        assert summary["consumed"] == model["actual"]
        assert summary["reserved"] == Amount().model_dump()


def test_direct_retry_guard_survives_development_bypass(classroom, monkeypatch):
    from tests.test_controls_execution import invoke, provider, response

    identity, store, policy, grants, auth_file, _ = classroom
    checkpoint(identity, store, policy)
    monkeypatch.setattr(settings, "controls_mode", "development_bypass")
    value, calls = provider([])

    def lose_policy(**kwargs):
        calls.append(kwargs)
        grants["teaching_policies"] = {}
        auth_file.write_text(json.dumps(grants))
        return response("invalid JSON")

    value._client.chat.completions.create = lose_policy
    with pytest.raises(HTTPException):
        invoke(teaching.guard_provider(identity, {}, value))
    assert len(calls) == 1


def test_lost_private_response_deduplicates_without_undoing_pause(classroom):
    identity, store, policy, _, _, _ = classroom
    enabled = store.update(
        identity,
        policy,
        "enable_0000000001",
        "enable",
        {"notice_version": NOTICE},
        expected_revision=0,
    )
    event = store.observe(
        identity,
        policy,
        "tool_denied",
        "hints_only",
        "policy_guidance",
        operation_id="same-operation",
    )
    revision = store.read(identity, policy)["revision"]
    action = (identity, policy, "challenge_0000001", "challenge", {"alert_id": event["alert_id"]})
    first = store.update(*action, expected_revision=revision)
    replay = store.update(*action, expected_revision=revision)
    assert first == replay  # Simulated response loss returns current state, no extra event.
    assert sum(e["action"] == "challenge" for e in replay["events"]) == 1
    paused = store.update(
        identity, policy, "pause_00000000001", "pause", expected_revision=replay["revision"]
    )
    replay = store.update(
        identity,
        policy,
        "enable_0000000001",
        "enable",
        {"notice_version": NOTICE},
        expected_revision=0,
    )
    assert replay["monitor"] == "paused" and replay["revision"] == paused["revision"]
    assert enabled["revision"] < replay["revision"]


def test_private_events_excluded_from_research_export_and_peer_routes(classroom, monkeypatch):
    from app import main
    from app.store import ConsentRouter, InMemoryStore, make_event
    from app.store.scoped import register, scoped_store

    identity, store, policy, _, _, _ = classroom
    router = ConsentRouter(InMemoryStore())
    monkeypatch.setattr(main, "_router", router)
    register(router, identity, True)
    scoped_store(router, identity).append_event(
        make_event(identity.learner_id, EX, "study", "run", {"ok": True})
    )
    store.update(identity, policy, "enable_0000000001", "enable", {"notice_version": NOTICE})
    event = store.observe(identity, policy, "tool_denied", "hints_only", "policy_guidance")
    client = TestClient(main.app)
    headers = {"Authorization": "Bearer " + token("synthetic-one")}
    result = client.get("/api/session/edu:1/events.jsonl", headers=headers)
    assert result.status_code == 200 and result.text.strip()
    assert event["alert_id"] not in result.text and "hints_only" not in result.text
    assert "tool_denied" not in result.text and "classroom_private" not in result.text
    assert client.get("/api/session/edu:2/events.jsonl", headers=headers).status_code == 404
    private_path = "/api/classroom/" + EX + "/" + VERSION
    for extra in ("/export", "/instructor", "/research"):
        assert client.get(private_path + extra, headers=headers).status_code == 404
    peer = client.get(private_path, headers={"Authorization": "Bearer " + token("synthetic-two")})
    assert peer.json()["alerts"] == {} and peer.json()["events"] == []


def test_saved_transaction_does_not_open_optional_second_writer(classroom, monkeypatch):
    _, store, _, _, _, _ = classroom
    monkeypatch.setattr(store, "observe", lambda *a, **kw: pytest.fail("second private writer"))
    uninitialized = object.__new__(ExecutionData)
    with pytest.raises(HTTPException) as denied:
        uninitialized.submit(
            classroom[0],
            "request_000000001",
            {"stance": "oracle"},
            "/api/conversations",
            connection=object(),
        )
    assert denied.value.detail["code"] == "hints_only"
