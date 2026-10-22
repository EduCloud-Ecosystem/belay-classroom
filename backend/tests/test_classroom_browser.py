# SPDX-License-Identifier: AGPL-3.0-only
"""Hermetic browser admission tests; no listener, provider or container execution."""

import asyncio
import hashlib
import json
from dataclasses import replace
from types import SimpleNamespace as NS

import pytest

from app.classroom.browser_demo import BrowserBoundary, metadata, reviewed_turn
from app.classroom.demo import EXERCISE, VERSION
from app.classroom.live_demo import mark_started, read_turn
from app.controls.contracts import ControlError
from tests.classroom_offline import deny_external  # noqa: F401
from tests.test_classroom_policy import classroom  # noqa: F401


@pytest.fixture
def browser():
    turn = {"message": "How can I check missing cells?", "source": "# synthetic work\n"}
    run = NS(
        operation="a" * 64,
        grant={"request_id": "synthetic_browser_request_01", "expires_at": 100},
        authority=lambda: None,
    )
    calls = []

    async def app(scope, receive, send):
        body = await receive() if scope["method"] == "POST" else None
        calls.append((scope["method"], scope["path"], body))
        await send({"type": "http.response.start", "status": 202, "headers": []})
        await send({"type": "http.response.body", "body": b"{}"})

    return BrowserBoundary(app, run, turn, "http://127.0.0.1:5188"), calls


def submit(boundary, method, path, body=None, chunks=None):
    responses = []
    incoming = list(
        chunks or [{"type": "http.request", "body": json.dumps(body).encode(), "more_body": False}]
    )

    async def receive():
        return incoming.pop(0) if incoming else {"type": "http.disconnect"}

    async def send(message):
        responses.append(message)

    asyncio.run(
        boundary(
            {
                "type": "http",
                "method": method,
                "path": path,
                "headers": [(b"origin", b"http://127.0.0.1:5188")],
            },
            receive,
            send,
        )
    )
    return responses


def payload(boundary):
    return {
        "request_id": boundary.run.grant["request_id"],
        "participant_id": "edu:2",
        "exercise_id": EXERCISE,
        "exercise_version": VERSION,
        "event": "chat",
        "source": boundary.turn["source"],
        "recent": [{"who": "student", "text": boundary.turn["message"]}],
        "mode": "study",
        "stance": "peer",
        "result": None,
    }


def test_exact_ask_passes_body_unchanged_without_execution(browser):
    boundary, calls = browser
    body = payload(boundary)
    response = submit(boundary, "POST", "/api/sol/jobs", body)
    assert response[0]["status"] == 202
    assert json.loads(calls[0][2]["body"]) == body


@pytest.mark.parametrize(
    "key,value",
    [
        ("request_id", "another_browser_request_01"),
        ("participant_id", "edu:1"),
        ("exercise_id", "different"),
        ("exercise_version", "old"),
        ("event", "run"),
        ("source", "changed"),
        ("recent", [{"who": "student", "text": "changed"}]),
        ("result", {"ok": True}),
        ("overlay", {"instruction": "unsafe"}),
        ("reply_to", {"request_id": "another_reply"}),
    ],
)
def test_wrong_or_injected_payload_denied_before_application(browser, key, value):
    boundary, calls = browser
    body = {**payload(boundary), key: value}
    response = submit(boundary, "POST", "/api/sol/jobs", body)
    assert response[0]["status"] == 403
    assert json.loads(response[1]["body"])["detail"]["code"] == "live_turn_not_granted"
    assert not calls


@pytest.mark.parametrize(
    "path",
    [
        "/api/run",
        "/api/sol/turn",
        "/quad/v1/turn",
        "/quad/v1/jobs",
        "/api/conversations",
        "/api/conversations/example/jobs",
        "/api/conversations/example/turns",
        "/api/sol/jobs/by-request/another_browser_request_01/reconcile",
    ],
)
def test_bypass_and_redispatch_routes_absent(browser, path):
    boundary, calls = browser
    response = submit(boundary, "POST", path, payload(boundary))
    assert response[0]["status"] == 403
    assert not calls


@pytest.mark.parametrize(
    "stance,mode", [("oracle", "study"), ("control", "study"), ("peer", "teach")]
)
def test_denied_modes_reach_existing_authenticated_teaching_policy(browser, stance, mode):
    boundary, calls = browser
    response = submit(
        boundary, "POST", "/api/sol/jobs", {**payload(boundary), "stance": stance, "mode": mode}
    )
    assert response[0]["status"] == 202
    assert len(calls) == 1  # Fake app only. Real app enforce() returns hints_only before admission.


@pytest.mark.parametrize(
    "path",
    [
        "/api/sol/jobs/config",
        "/api/sol/jobs/" + "a" * 64,
        "/api/sol/jobs/by-request/synthetic_browser_request_01",
        f"/api/classroom/{EXERCISE}/{VERSION}",
        "/api/conversations/config",
    ],
)
def test_reload_and_private_reads_only_call_existing_application(browser, path):
    boundary, calls = browser
    assert submit(boundary, "GET", path)[0]["status"] == 202
    assert len(calls) == 1


def test_foreign_result_or_expired_grant_denies_before_application(browser):
    boundary, calls = browser
    assert submit(boundary, "GET", "/api/sol/jobs/" + "b" * 64)[0]["status"] == 403

    def expired():
        raise ControlError("live_authority_unavailable", 503)

    boundary.run.authority = expired
    response = submit(boundary, "GET", "/api/sol/jobs/config")
    assert response[0]["status"] == 503
    assert (b"cache-control", b"no-store") in response[0]["headers"]
    assert not calls


def test_stream_limit_and_malformed_json_never_reach_application(browser):
    boundary, calls = browser
    chunks = [
        {"type": "http.request", "body": b"x" * 10000, "more_body": True},
        {"type": "http.request", "body": b"x" * 7000, "more_body": False},
    ]
    assert submit(boundary, "POST", "/api/sol/jobs", chunks=chunks)[0]["status"] == 413
    assert (
        submit(
            boundary,
            "POST",
            "/api/sol/jobs",
            chunks=[{"type": "http.request", "body": b"not-json"}],
        )[0]["status"]
        == 422
    )
    assert not calls


def test_browser_review_covers_frontend_and_turn(monkeypatch, tmp_path):
    from app.classroom import browser_demo

    path = tmp_path / "turn.json"
    value = {
        "message": "Synthetic question",
        "source": "# work",
        "schema_present": True,
        "unit_present": True,
        "declaration": "ai_assisted",
    }
    path.write_text(json.dumps(value))
    monkeypatch.setattr(browser_demo, "browser_source_manifest", lambda: ("assets-v1", {}))
    grant = {
        "browser_source_sha256": "assets-v1",
        "browser_turn_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }
    assert reviewed_turn(grant, path) == value
    with pytest.raises(ValueError, match="review"):
        reviewed_turn({**grant, "browser_source_sha256": "old"}, path)
    path.write_text(json.dumps({**value, "source": "changed"}))
    with pytest.raises(ValueError, match="review"):
        reviewed_turn(grant, path)
    path.write_text("x" * 8193)
    with pytest.raises(ValueError, match="bounded"):
        read_turn(path)


def test_public_metadata_has_no_private_authority(browser):
    boundary, _ = browser
    boundary.run.grant["provider_secret"] = "never expose"
    public = metadata(boundary.run, boundary.turn)
    assert set(public) == {
        "mode",
        "learner",
        "exercise_id",
        "exercise_version",
        "request_id",
        "expires_at",
        "message",
        "source",
    }
    assert "never expose" not in json.dumps(public)


def test_started_marker_is_durable_and_cannot_reset(tmp_path):
    grant = {
        key: "synthetic"
        for key in ("request_id", "reservation_id", "profile_sha256", "source_sha256")
    }
    grant["expires_at"] = 100
    run = NS(directory=tmp_path, operation="a" * 64, grant=grant)
    mark_started(run)
    original = (tmp_path / "run-started.json").read_bytes()
    with pytest.raises(FileExistsError):
        mark_started(run)
    assert (tmp_path / "run-started.json").read_bytes() == original


def test_expiry_during_body_read_prevents_application_call(browser):
    boundary, calls = browser
    replies = []

    async def receive():
        def expired():
            raise ControlError("live_authority_unavailable", 503)

        boundary.run.authority = expired
        return {
            "type": "http.request",
            "body": json.dumps(payload(boundary)).encode(),
            "more_body": False,
        }

    async def send(value):
        replies.append(value)

    asyncio.run(
        boundary({"type": "http", "method": "POST", "path": "/api/sol/jobs"}, receive, send)
    )
    assert replies[0]["status"] == 503 and not calls


def test_uncertain_shutdown_preserves_ownership_receipt(tmp_path):
    from app.classroom.browser_demo import confirm_stopped

    receipt, stop = tmp_path / "running.json", tmp_path / "stop.request"
    receipt.write_text("owned")
    stop.touch()
    blocks = []
    run = NS(block=blocks.append)
    with pytest.raises(RuntimeError, match="unconfirmed"):
        confirm_stopped(run, [NS(is_alive=lambda: True)], receipt, stop)
    assert receipt.read_text() == "owned" and stop.exists()
    assert blocks == ["live_listener_shutdown_unknown"]
    confirm_stopped(run, [NS(is_alive=lambda: False)], receipt, stop)
    assert not receipt.exists() and not stop.exists()


def test_real_authenticated_policy_admission_and_exact_recovery(classroom, ledger, monkeypatch):  # noqa: F811
    from cryptography.fernet import Fernet
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from app.auth import Membership, _grant_ref
    from app.controls import jobs_http
    from app.controls.admission import jobs
    from app.controls.data import ExecutionData
    from tests.http_auth import token
    from tests.test_classroom_policy import checkpoint

    identity, private, policy, grants, _, _ = classroom
    member = Membership(**grants["subjects"]["synthetic-two"][0])
    identity = replace(identity, learner_id="edu:2", grant_ref=_grant_ref("synthetic-two", member))
    store = ExecutionData(ledger, "browser-test", Fernet.generate_key())
    monkeypatch.setattr(jobs_http, "execution_store", lambda: store)
    app = FastAPI()
    app.include_router(jobs_http.build_jobs_router("/api/sol/jobs", NS(get_exercise=lambda _: {})))
    turn = {"source": "# synthetic work", "message": "How do I check missing cells?"}
    request_id = "real_browser_request_001"
    run = NS(
        operation=store.job_id(identity, request_id),
        grant={"request_id": request_id},
        authority=lambda: None,
    )
    boundary = BrowserBoundary(app, run, turn, "http://127.0.0.1:5188")
    client = TestClient(boundary, headers={"Authorization": "Bearer " + token("synthetic-two")})
    body = payload(boundary)
    config = client.get("/api/sol/jobs/config")
    assert config.status_code == 200 and config.json()["missing_request_recovery"] == 1
    denied = client.post("/api/sol/jobs", json={**body, "stance": "oracle"})
    assert denied.status_code == 403 and denied.json()["detail"]["code"] == "hints_only"
    missing_prediction = client.post("/api/sol/jobs", json=body)
    assert (
        missing_prediction.status_code == 409
        and missing_prediction.json()["detail"]["code"] == "prediction_required"
    )
    with ledger.transaction() as conn:
        assert list(conn.execute(select(jobs))) == []
    checkpoint(identity, private, policy)
    accepted = client.post("/api/sol/jobs", json=body)
    assert accepted.status_code == 202 and accepted.json()["id"] == run.operation
    assert client.post("/api/sol/jobs", json=body).json()["id"] == run.operation
    # Recover an admitted POST whose response was lost. The real reconcile route
    # only returns the existing queued job; no second job, provider or worker.
    context = {k: body[k] for k in ("request_id", "exercise_id", "exercise_version")}
    recovered = client.post("/api/sol/jobs/by-request/" + request_id + "/reconcile", json=context)
    assert recovered.status_code == 200 and recovered.json()["id"] == run.operation
    assert recovered.json()["state"] == "queued"
    with ledger.transaction() as conn:
        assert len(list(conn.execute(select(jobs)))) == 1
    assert client.post("/api/run", json=body).status_code == 403
    assert (
        client.post(
            "/api/sol/jobs", json=body, headers={"Authorization": "Bearer forged"}
        ).status_code
        == 401
    )
