# SPDX-License-Identifier: AGPL-3.0-only
"""Offline live-profile controls: synthetic credentials, no endpoint or container calls."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import select

from app.classroom.live_demo import (
    PROFILE,
    budget,
    read_inputs,
    read_key,
    read_profile,
    source_manifest,
)
from app.classroom.live_provider import LiveClassroomProvider, LiveRun, install, write_evidence
from app.classroom.live_runner import ContainerRunner, checked_inputs, checked_verdict
from app.config import settings
from app.controls.contracts import Amount, ControlError, Policy
from app.controls.ledger import attempts
from app.controls.runtime import attempt_reference, operation, reservation_guard, runner_call
from app.core import runner
from tests.classroom_offline import deny_external  # noqa: F401


def grant(tmp_path, profile):
    review = tmp_path / "review.json"
    review.write_text('{"source_only_review":true}')
    return {
        "profile_sha256": hashlib.sha256(PROFILE.read_bytes()).hexdigest(),
        "source_sha256": source_manifest()[0],
        "p1_profile_approved": True,
        "p1_review_path": str(review),
        "p1_review_sha256": hashlib.sha256(review.read_bytes()).hexdigest(),
        "root_execution_authorized": True,
        "runner_admitted": True,
        "runner_admission_evidence": "synthetic_runner_admission_001",
        "reservation_id": "synthetic_root_reservation_001",
        "request_id": "one_turn_request_001",
        "deployment_id": "live-test",
        "data_dir": str(tmp_path / "live"),
        "not_before": 10,
        "expires_at": 100,
        "reserved_microunits": profile["total_microunits"],
        "root_budget_total_microunits": 20000000,
        "other_held_or_spent_microunits": 10000,
    }


def reply(
    text='{"ok":true}', *, prompt=10, completion=5, model="gpt-6-luna", tier="default", usage=True
):
    return NS(
        choices=[NS(message=NS(content=text), finish_reason="stop")],
        usage=NS(
            prompt_tokens=prompt, completion_tokens=completion, total_tokens=prompt + completion
        )
        if usage
        else None,
        model=model,
        service_tier=tier,
        _request_id="req_synthetic",
    )


@pytest.fixture
def live(monkeypatch, ledger, tmp_path):
    profile = json.loads(PROFILE.read_bytes())
    value = grant(tmp_path, profile)
    directory = tmp_path / "live"
    directory.mkdir()
    (directory / "attempt-evidence").mkdir()
    grant_path = tmp_path / "grant.json"
    write_evidence(grant_path, value, new=True)
    write_evidence(directory / "live-grant.json", value, new=True)
    run = LiveRun(profile, value, directory, grant_path)
    monkeypatch.setattr("app.classroom.live_provider.time.time", lambda: 50)
    for name, setting in {
        "controls_mode": "enforced",
        "provider": "openai_compatible",
        "openai_base_url": profile["base_url"],
        "openai_model_fast": profile["model"],
        "openai_model_strong": profile["model"],
        "llm_billing_mode": "metered",
        "controls_inference_expires_at": 0,
        "controls_inference_total_microunits": profile["total_microunits"],
        "injection_guard_enabled": True,
        "distress_routing_enabled": True,
        "openai_final_content_only": True,
    }.items():
        monkeypatch.setattr(settings, name, setting)
    ledger.update_policy(Policy(**budget(profile)))
    replies, calls = [], []

    def create(**kwargs):
        calls.append(kwargs)
        item = replies.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item() if callable(item) else item

    monkeypatch.setattr(
        "app.classroom.live_provider.make_client",
        lambda _: NS(chat=NS(completions=NS(create=create))),
    )
    return LiveClassroomProvider(run), run, replies, calls


def invoke(provider, role="planner", **changes):
    values = {
        "role": role,
        "tier": "strong" if role == "reasoner" else "fast",
        "system": "s",
        "user": "u",
        "max_tokens": provider.run.profile["stages"][role]["output_tokens"],
    }
    return provider.json(**(values | changes))


def test_exact_grant_and_nonrenewing_budget(live):
    _, run, _, _ = live
    assert read_inputs(run.grant_path)[1] == run.grant
    policy = budget(run.profile)
    assert policy["deployment"] == {
        "tokens": 341252,
        "microunits": 350000,
        "runs": 8,
        "wall_ms": 168000,
    }
    assert all(
        policy[key + "_traffic"]["queue_jobs"] == 1
        for key in ("deployment", "institution", "classroom", "learner")
    )


def test_provisional_profile_matches_full_stage_reservation_formula():
    profile = read_profile()
    assert {role: stage["http_attempts"] for role, stage in profile["stages"].items()} == {
        "classifier": 1,
        "planner": 2,
        "reasoner": 8,
        "self_eval": 8,
    }
    assert (
        sum(
            stage["http_attempts"] * (profile["max_messages_bytes"] + 1024 + stage["output_tokens"])
            for stage in profile["stages"].values()
        )
        == profile["aggregate_tokens"]
        == 341252
    )
    assert profile["max_messages_bytes"] == 16384 and profile["max_attempts"] == 19
    assert profile["total_microunits"] == 350000


@pytest.mark.parametrize(
    "field,value",
    [
        ("max_messages_bytes", 6144),
        ("max_attempts", 30),
        ("aggregate_tokens", 341251),
        ("total_microunits", 250000),
        ("stages", {"classifier": {"http_attempts": 19, "output_tokens": 100}}),
    ],
)
def test_provisional_profile_rejects_stale_or_altered_formula(monkeypatch, tmp_path, field, value):
    profile = json.loads(PROFILE.read_bytes())
    profile[field] = value
    path = tmp_path / "changed-profile.json"
    path.write_text(json.dumps(profile))
    monkeypatch.setattr("app.classroom.live_demo.PROFILE", path)
    with pytest.raises(ValueError, match="live profile bounds changed"):
        read_profile()


@pytest.mark.parametrize(
    "field,value",
    [
        ("root_execution_authorized", False),
        ("runner_admitted", False),
        ("source_sha256", "b" * 64),
        ("profile_sha256", "c" * 64),
        ("expires_at", float("nan")),
        ("reserved_microunits", 250000),
    ],
)
def test_bad_grant_rejected(live, field, value):
    _, run, _, _ = live
    data = dict(run.grant)
    data[field] = value
    run.grant_path.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        read_inputs(run.grant_path)


def test_named_credential_is_data_not_shell(tmp_path):
    path = tmp_path / "credential.env"
    path.write_text(
        'UNRELATED=$(must_never_execute)\nOPENAI_API_KEY="synthetic_key_for_offline_test_001"\n'
    )
    path.chmod(0o600)
    assert read_key(path) == "synthetic_key_for_offline_test_001"
    path.write_text("OPENAI_API_KEY=$(must_never_execute)\n")
    with pytest.raises(ValueError):
        read_key(path)
    path.chmod(0o644)
    with pytest.raises(ValueError):
        read_key(path)


def test_reformat_preserves_wire_caps_effort_and_exact_accounting(live, ledger):
    provider, run, replies, calls = live
    replies.extend([reply("not json"), reply()])
    with operation(ledger, run.scope, run.operation):
        assert invoke(provider, "reasoner", reasoning_effort="high") == {"ok": True}
    assert len(calls) == 2
    for call in calls:
        assert call["max_completion_tokens"] == 800
        assert call["reasoning_effort"] == "high" and call["response_format"] == {
            "type": "json_object"
        }
        assert call["model"] == "gpt-6-luna" and call["service_tier"] == "default"
        assert (
            call["store"] is False
            and call["stream"] is False
            and call["n"] == 1
            and "tools" not in call
            and "tool_choice" not in call
        )
        assert "max_tokens" not in call and "temperature" not in call and "extra_body" not in call
    records = [
        json.loads(path.read_text())
        for path in (run.directory / "attempt-evidence").glob("model-*.json")
    ]
    assert {r["attempt_id"] for r in records} == {
        c["extra_headers"]["X-Client-Request-Id"] for c in calls
    }
    assert {r["format_attempt_index"] for r in records} == {1, 2}
    assert all(
        r["operation"] == run.operation and r["provider_request_id"] == "req_synthetic"
        for r in records
    )
    assert all(
        r["prompt_tokens"] == 10 and r["completion_tokens"] == 5 and r["estimated_microunits"] == 15
        for r in records
    )
    assert ledger.summary()["consumed"]["tokens"] == 30


@pytest.mark.parametrize(
    "role,expected",
    [("classifier", "none"), ("planner", "none"), ("self_eval", "none"), ("reasoner", "medium")],
)
def test_every_role_uses_pinned_model_and_effort(live, ledger, role, expected):
    provider, run, replies, calls = live
    replies.append(
        reply('{"flagged":false,"confidence":0.9}' if role == "classifier" else '{"ok":true}')
    )
    with operation(ledger, run.scope, run.operation):
        invoke(provider, role)
    assert calls[0]["reasoning_effort"] == expected


@pytest.mark.parametrize("usage", [False, True])
def test_missing_or_malformed_usage_is_unknown_and_stops(live, ledger, usage):
    provider, run, replies, calls = live
    result = reply(usage=usage)
    if usage:
        result.usage.prompt_tokens = True
    replies.append(result)
    with operation(ledger, run.scope, run.operation):
        with pytest.raises(ControlError, match="live_usage_unknown"):
            invoke(provider)
        with pytest.raises(ControlError, match="live_run_blocked"):
            invoke(provider)
    assert len(calls) == 1 and ledger.summary()["states"]["unknown"] == 1
    assert ledger.summary()["reserved"]["microunits"] > 0


@pytest.mark.parametrize("status", [400, 422, 401, None])
def test_transport_failures_never_retry_or_log_error_text(live, ledger, caplog, status):
    provider, run, replies, calls = live

    class Failed(Exception):
        status_code = status
        request_id = "req_synthetic_failure"

    replies.append(Failed("synthetic_secret_marker prompt/code must not appear"))
    with operation(ledger, run.scope, run.operation), pytest.raises(ControlError):
        invoke(provider)
    assert len(calls) == 1 and ledger.summary()["states"]["unknown"] == 1
    records = [path.read_text() for path in (run.directory / "attempt-evidence").glob("*.json")]
    assert "synthetic_secret_marker" not in "".join(records) + caplog.text
    assert json.loads(records[0])["provider_request_id"] == "req_synthetic_failure"


@pytest.mark.parametrize(
    "text",
    [
        '{"flagged":"false","confidence":0.9}',
        '{"flagged":false}',
        '{"flagged":false,"confidence":2}',
        '{"flagged":false,"confidence":null}',
        '{"flagged":false,"confidence":true}',
        '{"flagged":false,"confidence":false}',
        '{"flagged":false,"confidence":"0.9"}',
        '{"flagged":false,"confidence":NaN}',
        '{"flagged":false,"confidence":Infinity}',
        "not json",
        "[]",
    ],
)
def test_classifier_invalid_is_never_failed_open(live, ledger, monkeypatch, text):
    from app.agent import injection_guard, llm

    provider, run, replies, calls = live
    monkeypatch.setattr(llm, "_PROVIDERS", dict(llm._PROVIDERS))
    monkeypatch.setattr(injection_guard, "_guard_instance", None)
    install(run)
    replies.append(reply(text))
    with operation(ledger, run.scope, run.operation), pytest.raises(ControlError):
        injection_guard.get_guard().check("synthetic question")
    assert len(calls) == 1
    assert (run.directory / "run-blocked.json").is_file()


@pytest.mark.parametrize(
    "change", [{"model": "other-model"}, {"tier": "priority"}, {"completion": 401}]
)
def test_return_contract_failure_withholds_and_retains_actual_usage(live, ledger, change):
    provider, run, replies, calls = live
    replies.append(reply(**change))
    with operation(ledger, run.scope, run.operation), pytest.raises(ControlError):
        invoke(provider)
    assert len(calls) == 1 and ledger.summary()["consumed"]["tokens"] > 0
    assert (run.directory / "run-blocked.json").exists()


@pytest.mark.parametrize("boundary", ["input", "retry", "role_output"])
def test_actual_attempt_bounds_including_oversized_retry(live, ledger, boundary):
    provider, run, replies, calls = live
    changes = (
        {"user": "x" * (run.profile["max_messages_bytes"] + 1)}
        if boundary == "input"
        else {"max_tokens": 401}
        if boundary == "role_output"
        else {}
    )
    if boundary == "retry":
        replies.append(reply("x" * (run.profile["max_messages_bytes"] + 1)))
    with (
        operation(ledger, run.scope, run.operation),
        pytest.raises(ControlError, match="live_attempt_bounds_exceeded"),
    ):
        invoke(provider, **changes)
    assert len(calls) == (1 if boundary == "retry" else 0)


@pytest.mark.parametrize("boundary", ["expired", "revoked", "foreign"])
def test_authority_checked_before_dispatch(live, ledger, monkeypatch, boundary):
    provider, run, _, calls = live
    if boundary == "expired":
        monkeypatch.setattr("app.classroom.live_provider.time.time", lambda: 101)
    elif boundary == "revoked":
        run.grant_path.write_text(json.dumps(run.grant | {"root_execution_authorized": False}))
    job = "foreign-operation" if boundary == "foreign" else run.operation
    with operation(ledger, run.scope, job), pytest.raises(ControlError):
        invoke(provider)
    assert calls == [] and ledger.summary()["attempts"] == 0


def test_membership_revocation_withholds_before_dispatch(live, ledger):
    provider, run, replies, calls = live
    replies.append(reply())
    checks = 0

    def revoked():
        nonlocal checks
        checks += 1
        if checks >= 3:
            raise ControlError("authorization_revoked", 403)

    with operation(ledger, run.scope, run.operation, revoked), pytest.raises(ControlError):
        invoke(provider)
    assert calls == []


def test_postresponse_revocation_withholds_settled_reply(live, ledger):
    provider, run, replies, calls = live

    def revoked_response():
        run.grant_path.write_text(json.dumps(run.grant | {"root_execution_authorized": False}))
        return reply()

    replies.append(revoked_response)
    with (
        operation(ledger, run.scope, run.operation),
        pytest.raises(ControlError, match="live_authority_unavailable"),
    ):
        invoke(provider)
    assert len(calls) == 1 and ledger.summary()["consumed"]["tokens"] == 15
    assert (run.directory / "run-blocked.json").is_file()


def test_atomic_durable_cap_and_restart_do_not_replenish(live, ledger, monkeypatch):
    provider, run, replies, calls = live
    monkeypatch.setitem(run.profile, "max_attempts", 1)
    replies.append(reply())
    with operation(ledger, run.scope, run.operation):
        invoke(provider)
    restarted = LiveClassroomProvider(
        LiveRun(run.profile, run.grant, run.directory, run.grant_path)
    )
    with (
        operation(ledger, run.scope, run.operation),
        pytest.raises(ControlError, match="live_attempt_limit"),
    ):
        invoke(restarted)
    assert len(calls) == 1 and ledger.summary()["attempts"] == 1


def test_one_shot_marker_refuses_restart(live):
    _, run, _, _ = live
    marker = run.directory / "run-started.json"
    write_evidence(marker, {"operation": run.operation}, new=True)
    with pytest.raises(FileExistsError):
        write_evidence(marker, {"operation": "second-turn"}, new=True)
    assert json.loads(marker.read_text())["operation"] == run.operation


def test_second_inflight_reservation_denied_under_existing_transaction(live, ledger):
    provider, run, _, calls = live
    ledger.reserve("first", run.operation, run.scope, Amount(tokens=5), "model")
    with (
        operation(ledger, run.scope, run.operation),
        pytest.raises(ControlError, match="live_unresolved_or_foreign_attempt"),
    ):
        invoke(provider)
    assert calls == [] and ledger.summary()["attempts"] == 1


def test_existing_outer_runner_accounting_and_id_seam(live, ledger):
    _, run, _, _ = live
    seen = []

    def execute():
        seen.append(attempt_reference())
        return runner.RunnerResult(True, 0, "", "", False, 50, None)

    with operation(ledger, run.scope, run.operation), reservation_guard(run.reserve):
        runner_call(execute, 20)
    with ledger.transaction() as conn:
        row = conn.execute(select(attempts).where(attempts.c.id == seen[0])).mappings().one()
    assert row["kind"] == "runner" and row["actual"]["runs"] == 1


@pytest.mark.parametrize(
    "stdout",
    [
        "",
        "__GRADE__{}",
        "__GRADE__{}\n__GRADE__{}\n",
        "noise\n__GRADE__{}",
        '__GRADE__{"ok":true,"goalMet":false,"checks":[],"stdout":"","metric":null}',
        '__GRADE__{"ok":false,"goalMet":false,"checks":[],"stdout":"","metric":null,"error":"ImportError: missing"}',
    ],
)
def test_missing_malformed_duplicate_or_unavailable_verifier_aborts(stdout):
    with pytest.raises(ControlError, match="live_verifier_unavailable"):
        checked_verdict(stdout)


def test_strict_formative_verdict():
    value = {
        "ok": True,
        "goalMet": False,
        "metric": None,
        "stdout": "",
        "error": None,
        "checks": [
            {
                "type": "tidy_source_cells",
                "ok": False,
                "detail": "row_count: retain one row for every source country/year cell, including missing cells.",
            }
        ],
    }
    assert checked_verdict("__GRADE__" + json.dumps(value))["goal_met"] is False


def test_inputs_cannot_add_host_paths_or_replace_reviewed_harness(live):
    _, run, _, _ = live
    with pytest.raises(ControlError):
        checked_inputs("import os", {"../../key": "must not stage"}, [], run.profile["runner"])


def test_selected_runner_failure_never_falls_back_to_host():
    calls = []

    def unavailable(*args, **kwargs):
        calls.append(1)
        raise ControlError("live_runner_unavailable", 503)

    with (
        runner.execution_backend(unavailable),
        pytest.raises(ControlError, match="live_runner_unavailable"),
    ):
        runner._run_python("must never execute on host")
    assert calls == [1]


def test_container_unavailable_never_executes_host(live, monkeypatch):
    _, run, _, _ = live
    backend = ContainerRunner(run)
    monkeypatch.setattr(backend, "inspect", lambda *args, **kwargs: {"Id": "wrong-image"})
    with pytest.raises(ControlError, match="live_runner_image_mismatch"):
        backend.preflight()


def test_expiry_after_response_withholds_publication(live, ledger, monkeypatch):
    provider, run, replies, calls = live

    def late_response():
        monkeypatch.setattr("app.classroom.live_provider.time.time", lambda: 101)
        return reply()

    replies.append(late_response)
    with (
        operation(ledger, run.scope, run.operation),
        pytest.raises(ControlError, match="live_authority_unavailable"),
    ):
        invoke(provider)
    assert len(calls) == 1 and ledger.summary()["consumed"]["tokens"] == 15


@pytest.mark.parametrize("failure", [None, "timeout", "stdio_limit", "malformed", "teardown"])
def test_owned_container_teardown_and_verifier_failure_states(live, ledger, monkeypatch, failure):
    from app.classroom.assignments import EXERCISE
    from app.classroom.live_runner import ROOT

    _, run, _, _ = live
    verdict = {
        "ok": True,
        "goalMet": False,
        "metric": None,
        "stdout": "",
        "error": None,
        "checks": [
            {
                "type": "nhanes_participant_readings",
                "ok": False,
                "detail": "row_count: retain three readings for every selected demographic participant, including missing cells.",
            }
        ],
    }
    output = b"__GRADE__" + json.dumps(verdict).encode()
    files = {
        "spec.json": (ROOT / "packs/datascience/specs" / (EXERCISE + ".json")).read_text(),
        "nhanes_check.py": (ROOT / "packs/datascience/nhanes_check.py").read_text(),
        **{
            name: (ROOT / "packs/datascience/specs" / name).read_bytes()
            for name in ("data/DEMO_L_selected.csv", "data/BPXO_L_selected.csv")
        },
        "student.py": "# synthetic source; never executed in this test",
    }
    calls = []
    state = {}
    backend = ContainerRunner(run)

    def inspect(target, image=False):
        if image:
            return {"Id": run.profile["runner"]["image_id"]}
        return state

    def cli(*args, seconds=5):
        calls.append(args[0])
        if args[0] == "create":
            mounts = []
            for i, arg in enumerate(args):
                if arg == "--mount":
                    parts = dict(
                        item.split("=", 1) for item in args[i + 1].split(",") if "=" in item
                    )
                    mounts.append(
                        {
                            "Destination": parts["dst"],
                            "Source": parts["src"],
                            "RW": False,
                            "Type": "bind",
                        }
                    )
            labels = dict(
                args[i + 1].split("=", 1) for i, arg in enumerate(args) if arg == "--label"
            )
            state.update(
                Image=run.profile["runner"]["image_id"],
                Mounts=mounts,
                Config={"User": "65534:65534", "Labels": labels},
                HostConfig={
                    "ReadonlyRootfs": True,
                    "NetworkMode": "none",
                    "Memory": 536870912,
                    "MemorySwap": 536870912,
                    "NanoCpus": 1000000000,
                    "PidsLimit": 32,
                    "Privileged": False,
                    "PidMode": "",
                    "IpcMode": "private",
                    "CapDrop": ["ALL"],
                    "SecurityOpt": ["no-new-privileges"],
                    "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=67108864,mode=1777"},
                },
                State={"Running": False, "OOMKilled": False, "ExitCode": 0},
            )
            return 0, b"a" * 64 + b"\n", b"", None
        if args[0] == "start":
            state["State"]["Running"] = failure == "timeout"
            return (
                0,
                b"bad" if failure == "malformed" else output,
                b"",
                failure if failure in {"timeout", "stdio_limit"} else None,
            )
        if args[0] == "kill":
            state["State"]["Running"] = False
        if args[0] == "rm" and failure == "teardown":
            return 1, b"", b"private daemon error", None
        return 0, b"", b"", None

    monkeypatch.setattr(backend, "inspect", inspect)
    monkeypatch.setattr(backend, "cli", cli)
    source = (ROOT / "packs/datascience/_harness.py").read_text()
    with operation(ledger, run.scope, run.operation), reservation_guard(run.reserve):
        if failure:
            with pytest.raises(ControlError):
                runner_call(lambda: backend(source, files=files), 20)
        else:
            result = runner_call(lambda: backend(source, files=files), 20)
            assert result.ok and checked_verdict(result.stdout, EXERCISE)["goal_met"] is False
    assert "rm" in calls
    if failure == "timeout":
        assert "kill" in calls
    record = json.loads(
        next((run.directory / "attempt-evidence").glob("runner-*.json")).read_text()
    )
    assert record["stopped_confirmed"] is True
    assert record["removed_confirmed"] is (failure != "teardown")
    assert "private daemon error" not in json.dumps(record)
    assert (
        ledger.summary()["states"]["unknown"] == 1
        if failure
        else ledger.summary()["consumed"]["runs"] == 1
    )


def _tidy_record(check_ok, detail):
    return "__GRADE__" + json.dumps(
        {
            "ok": True,
            "goalMet": check_ok,
            "metric": None,
            "error": None,
            "stdout": "",
            "checks": [{"type": "tidy_source_cells", "ok": check_ok, "detail": detail}],
        }
    )


@pytest.mark.parametrize(
    "check_ok,detail",
    [
        (False, "columns: provide country, year, annual_inflation in that order."),
        (
            False,
            "row_count: retain one row for every source country/year cell, including missing cells.",
        ),
        (False, "method: use the assignment's melt() or pivot_table() requirement."),
        (True, "All source cells, keys and missingness retained (row order ignored)."),
    ],
)
def test_verifier_accepts_truthful_known_formative_details(check_ok, detail):
    assert checked_verdict(_tidy_record(check_ok, detail))["goal_met"] is check_ok


@pytest.mark.parametrize(
    "check_ok,detail",
    [
        (False, "ValueError: invalid instructor source"),
        (False, "NameError: tidy_checker is unavailable"),
        (False, "missingness: unknown checker outcome"),
        (
            False,
            "columns: provide country, year, annual_inflation in that order. ValueError: failed",
        ),
        (False, "All source cells, keys and missingness retained (row order ignored)."),
        (True, "columns: provide country, year, annual_inflation in that order."),
        (True, "made up successful check"),
    ],
)
def test_verifier_rejects_checker_errors_unknown_or_untruthful_details(check_ok, detail):
    with pytest.raises(ControlError, match="live_verifier_unavailable"):
        checked_verdict(_tidy_record(check_ok, detail))


@pytest.fixture
def queued_real_loop(live, ledger, monkeypatch, tmp_path):
    """Real queue/context/retrieval/governance; only external execution is scripted."""
    from cryptography.fernet import Fernet

    from app.agent import governance, injection_guard, llm
    from app.auth import Identity, Membership, _grant_ref
    from app.classroom import policy as teaching
    from app.classroom.assignments import EXERCISE, NHANES, VERSION
    from app.classroom.demo import authorization
    from app.classroom.store import PrivateStore
    from app.classroom.store import metadata as private_metadata
    from app.controls.data import ExecutionData
    from app.controls.jobs_worker import AskAdapter
    from app.core.registry import get_active_pack
    from app.packs.datascience import grader
    from app.store import ConsentRouter, InMemoryStore
    from tests.http_auth import configure

    provider, run, replies, sdk_calls = live
    monkeypatch.setenv("TUTOR_PACK", "datascience")
    for name, value in {
        "max_refine": 1,
        "max_escalate": 1,
        "max_worked_example_retry": 1,
        "reasoner_effort_default": "medium",
        "reasoner_effort_escalated": "high",
    }.items():
        monkeypatch.setattr(settings, name, value)
    auth = authorization(*NHANES)
    configure(monkeypatch, tmp_path, auth)
    member = Membership(**auth["subjects"]["synthetic-two"][0])
    identity = Identity(
        member.institution_id,
        member.class_id,
        member.learner_id,
        tuple(member.assignments.items()),
        EXERCISE,
        VERSION,
        tuple(member.assignments.items()),
        _grant_ref("synthetic-two", member),
    )
    private_metadata.create_all(ledger.engine)
    private = PrivateStore(ledger.engine, now=lambda: 50)
    monkeypatch.setattr(teaching, "configured_store", lambda: private)
    private.update(
        identity,
        teaching.policy_for(identity),
        "prediction_00000001",
        "checkpoint",
        {"schema_present": True, "unit_present": True},
    )
    store = ExecutionData(ledger, run.scope.deployment, Fernet.generate_key())
    pack = get_active_pack()
    kb = pack.knowledge()
    searches, grade_sources, governance_calls = [], [], []
    search = kb.search

    def real_search(query, k):
        passages = search(query, k)
        searches.append({"retrieved": len(passages), "ids": [passage.id for passage in passages]})
        return passages

    monkeypatch.setattr(kb, "search", real_search)
    example_source = "print('synthetic analogy')"
    example_checks = 0

    def execution_outcome(source, exercise):
        # A fake external verdict, not a replacement for search/leak/governance.
        # No source, notebook, runner or process is executed in this test.
        nonlocal example_checks
        grade_sources.append(hashlib.sha256(source.encode()).hexdigest())
        if source == example_source:
            example_checks += 1
        ok = source != example_source or example_checks > 1
        return {
            "ok": ok,
            "goalMet": False,
            "metric": None,
            "error": None if ok else "ValueError: scripted invalid analogy",
            "pack": {
                "id": "datascience",
                "stdout": "",
                "checks": [],
                "execution_status": "completed" if ok else "student_error",
            },
        }

    monkeypatch.setattr(grader, "grade", execution_outcome)
    check = governance.check

    def real_governance(ctx, plan, draft, evaluation, **kwargs):
        outcome = check(ctx, plan, draft, evaluation, **kwargs)
        governance_calls.append(
            {
                "exercise_id": ctx["_exercise_full"]["id"],
                "block": outcome["block"],
                "flag": outcome["flag"],
            }
        )
        return outcome

    monkeypatch.setattr(governance, "check", real_governance)
    monkeypatch.setattr(llm, "_PROVIDERS", dict(llm._PROVIDERS))
    monkeypatch.setattr(injection_guard, "_guard_instance", None)
    install(run)
    approved_turn = json.loads(
        (Path(__file__).parent / "fixtures/classroom/nhanes-turn.json").read_text()
    )
    payload = {
        "participant_id": "edu:2",
        "exercise_id": EXERCISE,
        "mode": "study",
        "stance": "peer",
        "event": "chat",
        "source": approved_turn["source"],
        "recent": [{"who": "student", "text": approved_turn["message"]}],
    }
    job = store.submit(identity, run.grant["request_id"], payload, "/api/sol/jobs")
    assert job["id"] == run.operation
    adapter = AskAdapter(store, ConsentRouter(InMemoryStore()), pack, llm.get_llm)
    return NS(
        provider=provider,
        run=run,
        replies=replies,
        sdk_calls=sdk_calls,
        store=store,
        identity=identity,
        adapter=adapter,
        searches=searches,
        grade_sources=grade_sources,
        governance_calls=governance_calls,
        example_source=example_source,
    )


def _record_real_stage_attempts(monkeypatch, queued, *, measure_only):
    """Record exact serialized bodies before bounds; never persist prompt content."""
    original = LiveClassroomProvider._attempt
    frames = []
    evaluations = 0

    def scripted(role):
        nonlocal evaluations
        if role == "classifier":
            return {"flagged": False, "confidence": 0.9}
        if role == "planner":
            return {
                "affective_state": "productive_struggle",
                "affect_reasoning": "Synthetic practice",
                "intervention": "worked_analogy",
                "target_concept": "observational units",
                "planner_note": "Compare a small unrelated example",
                "confidence": 0.8,
            }
        if role == "reasoner":
            return {
                "message": "Which cells should be represented in each observation?",
                "check_question": "How will you count missing observations?",
                "confidence": 0.8,
                "grasped": [],
                "shaky": [],
                "worked_example": {"source": queued.example_source},
            }
        evaluations += 1
        return {
            "needs_revision": evaluations == 1,
            "confidence": 0.4 if evaluations <= 2 else 0.8,
            "leak_risk": "none",
            "self_critique": "Make the next check concrete",
            "reasons": ["clarify check"],
        }

    def recorded(self, role, kwargs):
        messages = json.dumps(kwargs["messages"], ensure_ascii=False)
        frame = {
            "role": role,
            "format_attempt_index": kwargs["format_attempt_index"],
            "reasoning_effort": kwargs["reasoning_effort"],
            "output_tokens": kwargs["max_tokens"],
            "messages_bytes": len(messages.encode()),
            "messages_sha256": hashlib.sha256(messages.encode()).hexdigest(),
        }
        if role in {"planner", "reasoner"}:
            user = kwargs["messages"][1]["content"]
            ctx = json.loads(
                user
                if role == "planner"
                else user.removeprefix("CONTEXT:\n").split("\n\nCHOSEN PLAN FOR THIS TURN:\n", 1)[0]
            )
            frame["full_exercise_preserved"] = (
                ctx["_exercise_full"]["id"] == queued.identity.exercise_id
            )
            frame["duplicated_prompt_preserved"] = (
                ctx["_exercise_full"]["prompt"] == ctx["exercise"]["prompt"]
            )
            frame["retrieval_count"] = ctx["_retrieval"]["retrieved"]
            frame["knowledge_passages"] = len(ctx["knowledge"])
        frames.append(frame)
        if measure_only:
            # Test-only measurement shim bypasses actual dispatch/admission so
            # every later real-loop prompt can be measured despite today's cap.
            # Production profile, prompts and authority are never changed.
            text = (
                "malformed synthetic JSON"
                if role != "classifier" and kwargs["format_attempt_index"] == 1
                else json.dumps(scripted(role))
            )
            return reply(text)
        queued.replies.append(reply(json.dumps(scripted(role))))
        return original(self, role, kwargs)

    monkeypatch.setattr(LiveClassroomProvider, "_attempt", recorded)
    return frames


def _report_stage_measurements(queued, frames):
    report = {
        "scope": "offline_scripted_full_queued_loop_not_live_acceptance",
        "profile_cap_bytes": queued.run.profile["max_messages_bytes"],
        "attempts": frames,
        "retrieval": queued.searches,
        "verifier_invocations": len(queued.grade_sources),
        "final_governance": queued.governance_calls,
    }
    print(json.dumps(report, sort_keys=True))
    return report


def test_full_queued_safety_loop_fits_current_live_message_cap(queued_real_loop, monkeypatch):
    """Measure real safety prompts against the exact unreleased provisional envelope."""
    from app.controls.worker import run_one

    queued = queued_real_loop
    frames = _record_real_stage_attempts(monkeypatch, queued, measure_only=True)
    assert run_one(queued.store.admission, queued.adapter)
    status = queued.store.status(queued.identity, queued.run.operation)
    _report_stage_measurements(queued, frames)
    assert status["state"] == "completed"
    assert queued.sdk_calls == []  # measurement never sends even to fake SDK
    assert queued.searches and queued.searches[0]["retrieved"] > 0
    assert queued.grade_sources and queued.governance_calls
    assert [frame["role"] for frame in frames].count("classifier") == 1
    assert [frame["role"] for frame in frames].count("planner") == 2
    assert [frame["role"] for frame in frames].count("reasoner") == 8
    assert [frame["role"] for frame in frames].count("self_eval") == 8
    assert len(frames) == queued.run.profile["max_attempts"] == 19
    # Measured with the approved eight-line NHANES cell and actual question;
    # retain the existing cap, every safety stage and all retrieval passages.
    assert max(frame["messages_bytes"] for frame in frames) == 16233
    assert (
        max(frame["messages_bytes"] for frame in frames) <= queued.run.profile["max_messages_bytes"]
    )
    assert (
        sum(
            queued.run.profile["max_messages_bytes"] + 1024 + frame["output_tokens"]
            for frame in frames
        )
        == queued.run.profile["aggregate_tokens"]
        == 341252
    )
    assert (
        sum(frame["messages_bytes"] + 1024 + frame["output_tokens"] for frame in frames)
        <= queued.run.profile["aggregate_tokens"]
    )
    context_frames = [frame for frame in frames if frame["role"] in {"planner", "reasoner"}]
    assert all(
        frame["full_exercise_preserved"] and frame["duplicated_prompt_preserved"]
        for frame in context_frames
    )
    assert {frame["reasoning_effort"] for frame in frames if frame["role"] == "reasoner"} == {
        "medium",
        "high",
    }
    oversized = [
        {
            "role": frame["role"],
            "index": frame["format_attempt_index"],
            "bytes": frame["messages_bytes"],
        }
        for frame in frames
        if frame["messages_bytes"] > queued.run.profile["max_messages_bytes"]
    ]
    assert not oversized, json.dumps({"actual_prompt_contract_exceeded": oversized}, sort_keys=True)


def test_actual_queued_prompt_bounds_withhold_before_oversized_dispatch(
    queued_real_loop, monkeypatch
):
    from app.controls.admission import jobs
    from app.controls.worker import run_one

    queued = queued_real_loop
    # This deliberately undersized TEST profile preserves the original real-loop
    # rejection control after the proposed production cap increases. It grants nothing.
    monkeypatch.setitem(queued.run.profile, "max_messages_bytes", 6144)
    frames = _record_real_stage_attempts(monkeypatch, queued, measure_only=False)
    assert run_one(queued.store.admission, queued.adapter)
    _report_stage_measurements(queued, frames)
    oversized = [
        frame
        for frame in frames
        if frame["messages_bytes"] > queued.run.profile["max_messages_bytes"]
    ]
    assert oversized
    assert len(queued.sdk_calls) < len(frames)
    with queued.store.ledger.transaction() as conn:
        row = conn.execute(select(jobs).where(jobs.c.id == queued.run.operation)).mappings().one()
    assert row["state"] == "failed" and row["reason"] == "live_attempt_bounds_exceeded"
    assert row["result_ref"] is None
    assert (queued.run.directory / "run-blocked.json").is_file()


def test_launcher_refreshes_bob_token_before_long_job_result_read(
    live, ledger, monkeypatch, tmp_path
):
    """Simulated completion at 301s: exercise real launcher token refresh, no inference."""
    from contextlib import nullcontext

    import fastapi.testclient

    from app.classroom import live_demo, live_provider
    from app.controls import jobs_http, worker

    _, run, _, _ = live
    clock = [50.0]
    run.grant["expires_at"] = 900
    run.grant_path.write_text(json.dumps(run.grant))
    (run.directory / "live-grant.json").write_text(json.dumps(run.grant))
    monkeypatch.setattr(live_provider.time, "time", lambda: clock[0])
    turn = tmp_path / "synthetic-turn.json"
    turn.write_text(
        json.dumps(
            {
                "message": "How can I check missing cells?",
                "source": "# synthetic work",
                "schema_present": True,
                "unit_present": True,
                "declaration": "ai_assisted",
            }
        )
    )
    token_times, clients = [], []

    class Host:
        def token(self):
            token_times.append(clock[0])
            return "synthetic-token-" + str(int(clock[0]))

    class Client:
        def __init__(self, app, headers):
            self.headers = dict(headers)
            self.revision = 0
            clients.append(self)

        def get(self, path, **kwargs):
            if path.startswith("/api/sol/jobs/"):
                effective = self.headers | kwargs.get("headers", {})
                assert effective["Authorization"] == "Bearer synthetic-token-351"
                return NS(
                    status_code=200,
                    json=lambda: {
                        "state": "completed",
                        "reason": None,
                        "result": {"message": "A synthetic released hint", "check_question": None},
                    },
                )
            return NS(status_code=200, json=lambda: {"revision": self.revision})

        def post(self, path, json):
            if path == "/api/sol/jobs":
                return NS(status_code=202, json=lambda: {"id": run.operation})
            self.revision += 1
            revision = self.revision
            return NS(status_code=200, json=lambda: {"revision": revision})

    def completed_after_original_token_expired(*args):
        clock[0] = 351.0
        return True

    store = NS(ledger=ledger, admission=NS())
    monkeypatch.setattr(jobs_http, "execution_store", lambda: store)
    monkeypatch.setattr(fastapi.testclient, "TestClient", Client)
    bindings = []
    monkeypatch.setattr(live_demo, "check_binding", lambda *args: bindings.append(args[1:]))
    monkeypatch.setattr(live_demo, "bind_learner", lambda runtime, learner: None)
    monkeypatch.setattr(ContainerRunner, "preflight", lambda self: None)
    monkeypatch.setattr(live_provider, "install", lambda run: None)
    monkeypatch.setattr(live_provider, "wall_deadline", lambda seconds: nullcontext())
    monkeypatch.setattr(worker, "run_one", completed_after_original_token_expired)
    runtime = NS(runtime_host=lambda directory, manifest: Host(), load=lambda directory: {})
    result = live_demo.run_turn(
        runtime, run.directory, run.profile, run.grant, run.grant_path, turn
    )
    assert result["state"] == "completed"
    assert token_times == [50.0, 351.0] and len(clients) == 1
    from app.classroom.assignments import NHANES

    assert bindings == [NHANES]


@pytest.fixture
def purge_installation(monkeypatch, tmp_path):
    from cryptography.fernet import Fernet
    from sqlalchemy import create_engine

    from app.classroom import store as private_store
    from app.classroom.demo import authorization
    from app.controls import jobs_http
    from app.controls.data import ExecutionData, data
    from app.controls.ledger import Ledger

    directory = tmp_path / "dedicated-live"
    directory.mkdir()
    engine = create_engine("sqlite:///" + str(directory / "belay.sqlite3"))
    ledger = Ledger(engine, lambda: 100)
    ledger.initialize(Policy(**budget(json.loads(PROFILE.read_bytes()))))
    private_store.metadata.create_all(engine)
    execution = ExecutionData(ledger, "dedicated-live", Fernet.generate_key())
    private = private_store.PrivateStore(engine, now=lambda: 100)
    monkeypatch.setattr(jobs_http, "execution_store", lambda: execution)
    monkeypatch.setattr(private_store, "configured_store", lambda: private)
    write_evidence(directory / "authorization.json", authorization(), new=True)
    for name in ("run-started.json", "run-blocked.json", "attempt-evidence.json"):
        write_evidence(directory / name, {"synthetic_evidence": name}, new=True)
    with ledger.transaction() as conn:
        conn.execute(
            private_store.sessions.insert().values(
                owner="a" * 64,
                revision=1,
                expires=100000,
                body=private._empty() | {"checkpoint": True},
            )
        )
        conn.execute(
            data.insert().values(
                id="b" * 32,
                job="c" * 64,
                kind="result",
                body=execution.cipher.encrypt(b'{"message":"synthetic private content"}').decode(),
                bytes=39,
                expires=100000,
            )
        )
    from app.controls.contracts import Scope

    scope = Scope("dedicated-live", "synthetic-inst", "synthetic-class", "edu:2")
    ledger.reserve(
        "unknown_attempt", "unknown_operation", scope, Amount(tokens=5, microunits=5), "model"
    )
    ledger.settle("unknown_attempt", None)
    yield NS(directory=directory, ledger=ledger, execution=execution, private=private)
    engine.dispose()


def _seed_cleanup_job(installation, state):
    from app.controls.admission import jobs

    with installation.ledger.transaction() as conn:
        conn.execute(
            jobs.insert().values(
                id="d" * 64,
                operation="terminal_or_active_job",
                scopes=["e" * 64],
                fingerprint="f" * 64,
                payload_ref=None,
                payload_bytes=1,
                result_ref=None,
                state=state,
                reason=None,
                created=100,
                expires=100000,
                lease=None,
                deadline=None,
                fence=0,
                last_poll=None,
                sequence=1,
            )
        )


def _purge_state(installation):
    from app.classroom.store import sessions
    from app.controls.admission import jobs
    from app.controls.data import data

    with installation.ledger.transaction() as conn:
        return {
            "sessions": [dict(row) for row in conn.execute(select(sessions)).mappings()],
            "data": [dict(row) for row in conn.execute(select(data)).mappings()],
            "attempts": [dict(row) for row in conn.execute(select(attempts)).mappings()],
            "jobs": [dict(row) for row in conn.execute(select(jobs)).mappings()],
        }


def test_dedicated_purge_removes_fresh_private_content_and_preserves_unknown_accounting(
    purge_installation,
):
    from app.classroom.live_demo import cleanup_private_installation

    installation = purge_installation
    _seed_cleanup_job(installation, "failed")
    before = _purge_state(installation)
    markers = {
        path.name: path.read_bytes()
        for path in installation.directory.glob("*.json")
        if path.name != "authorization.json"
    }
    assert before["sessions"][0]["expires"] > 100 and before["data"][0]["expires"] > 100
    result = cleanup_private_installation(installation.directory)
    after = _purge_state(installation)
    assert after["sessions"] == [] and after["data"] == []
    assert after["attempts"] == before["attempts"] and after["jobs"] == before["jobs"]
    assert after["attempts"][0]["state"] == "unknown" and after["attempts"][0]["actual"] is None
    assert json.loads((installation.directory / "authorization.json").read_text())["subjects"] == {}
    assert {name: (installation.directory / name).read_bytes() for name in markers} == markers
    assert result["private_rows_deleted"] == 1 and result["encrypted_rows_deleted"] == 1
    assert result["secure_erasure_claimed"] is False


@pytest.mark.parametrize("state", ["queued", "running", "cancel_requested", "unknown"])
def test_dedicated_purge_refuses_active_or_uncertain_job_without_mutation(
    purge_installation, state
):
    from app.classroom.live_demo import cleanup_private_installation

    installation = purge_installation
    _seed_cleanup_job(installation, state)
    before = _purge_state(installation)
    auth = (installation.directory / "authorization.json").read_bytes()
    with pytest.raises(ControlError, match="live_cleanup_active_work"):
        cleanup_private_installation(installation.directory)
    assert _purge_state(installation) == before
    assert (installation.directory / "authorization.json").read_bytes() == auth


def test_dedicated_purge_refuses_a_sibling_database(purge_installation, monkeypatch, tmp_path):
    from cryptography.fernet import Fernet
    from sqlalchemy import create_engine

    from app.classroom.live_demo import cleanup_private_installation
    from app.controls import jobs_http
    from app.controls.data import ExecutionData
    from app.controls.ledger import Ledger

    installation = purge_installation
    sibling = create_engine("sqlite:///" + str(tmp_path / "sibling.sqlite3"))
    other = ExecutionData(Ledger(sibling), "sibling", Fernet.generate_key())
    monkeypatch.setattr(jobs_http, "execution_store", lambda: other)
    before = _purge_state(installation)
    try:
        with pytest.raises(ControlError, match="live_cleanup_database_mismatch"):
            cleanup_private_installation(installation.directory)
    finally:
        sibling.dispose()
    assert _purge_state(installation) == before
    assert json.loads((installation.directory / "authorization.json").read_text())["subjects"]


@pytest.fixture
def real_sdk_client(monkeypatch):
    """Construct the installed SDK to exercise its http_client type check, no request."""
    from app.classroom.live_provider import make_client

    profile = read_profile()
    monkeypatch.setattr(settings, "openai_api_key", "synthetic_sdk_construction_key_001")
    client = make_client(profile)
    try:
        yield profile, client
    finally:
        client.close()
        assert client._client.is_closed


def test_real_sdk_client_uses_compatible_bounded_transport(real_sdk_client):
    import httpx2
    from openai import DefaultHttpxClient

    profile, client = real_sdk_client
    http_client = client._client
    assert isinstance(http_client, DefaultHttpxClient)
    assert isinstance(http_client, httpx2.Client)
    assert client.max_retries == 0
    assert http_client.follow_redirects is False and http_client.trust_env is False
    assert http_client._mounts == {}  # No environment-proxy transports.
    assert all(
        getattr(http_client.timeout, kind) == float(profile["http_wall_seconds"])
        for kind in ("connect", "read", "write", "pool")
    )
    transport = http_client._transport
    assert isinstance(transport, httpx2.BaseTransport)
    assert isinstance(transport.inner, httpx2.HTTPTransport)
    assert transport.inner._pool._retries == 0
    assert transport.inner._pool._max_connections == 1
    assert transport.inner._pool._max_keepalive_connections == 1


def test_sdk_transport_rejects_incompatible_default_client(monkeypatch):
    import httpx
    import openai

    from app.classroom.live_provider import make_client

    monkeypatch.setattr(openai, "DefaultHttpxClient", httpx.Client)
    with pytest.raises(ControlError, match="live_sdk_transport_incompatible"):
        make_client(read_profile())


@pytest.mark.parametrize("overflow", [False, True])
def test_real_sdk_transport_enforces_stream_byte_cap_without_network(
    real_sdk_client, monkeypatch, overflow
):
    import httpx2

    profile, client = real_sdk_client
    transport = client._client._transport
    transport.inner.close()  # No open connections; replace only the inner network seam.
    closed, requests = [], []

    class Source(httpx2.SyncByteStream):
        def __iter__(self):
            yield b"x" * profile["max_http_response_bytes"]
            if overflow:
                yield b"y"

        def close(self):
            closed.append(True)

    def handle(request):
        requests.append(str(request.url))
        return httpx2.Response(200, stream=Source())

    monkeypatch.setattr(transport, "inner", NS(handle_request=handle, close=lambda: None))
    endpoint = profile["base_url"] + "/chat/completions"
    response = transport.handle_request(httpx2.Request("POST", endpoint))
    try:
        assert isinstance(response.stream, httpx2.SyncByteStream)
        if overflow:
            with pytest.raises(ControlError, match="live_response_byte_limit"):
                response.read()
        else:
            assert len(response.read()) == profile["max_http_response_bytes"]
    finally:
        response.close()
    assert requests == [endpoint] and closed


def test_real_sdk_transport_rejects_other_endpoint_before_inner_send(real_sdk_client, monkeypatch):
    import httpx2

    _, client = real_sdk_client
    transport = client._client._transport
    transport.inner.close()
    requests = []
    monkeypatch.setattr(
        transport,
        "inner",
        NS(handle_request=lambda request: requests.append(request), close=lambda: None),
    )
    with pytest.raises(ControlError, match="live_endpoint_mismatch"):
        transport.handle_request(
            httpx2.Request("POST", "https://wrong-endpoint.invalid/chat/completions")
        )
    assert requests == []


def test_distribution_metadata_reports_actual_live_http_client():
    from importlib.metadata import version

    from app.classroom.live_demo import distribution_versions

    reported = distribution_versions()
    assert reported["httpx2"] == version("httpx2")
    assert reported["httpx"] == version("httpx")  # Separate TestClient dependency retained.


def test_bounded_process_reads_selector_stable_fd(monkeypatch):
    import selectors

    from app.classroom import live_runner

    class Pipe:
        def __init__(self, fd):
            self.fd = fd

        def fileno(self):
            return self.fd

        def close(self):
            pass

    class Process:
        def __init__(self):
            self.stdout, self.stderr = Pipe(11), Pipe(12)
            self.returncode = None

        def wait(self, timeout):
            self.returncode = 0
            return 0

        def poll(self):
            return self.returncode

        def kill(self):
            self.returncode = -9

    class Selector:
        def __init__(self):
            self.keys = {}

        def register(self, fileobj, events, data):
            fd = fileobj.fileno()
            self.keys[fd] = selectors.SelectorKey(fd, fd, events, data)

        def unregister(self, fileobj):
            self.keys.pop(fileobj)

        def get_map(self):
            return self.keys

        def select(self, timeout):
            return [(key, selectors.EVENT_READ) for key in self.keys.values()]

        def close(self):
            pass

    reads = {11: [b"bounded output", b""], 12: [b""]}
    monkeypatch.setattr(live_runner.subprocess, "Popen", lambda *args, **kwargs: Process())
    monkeypatch.setattr(live_runner.selectors, "DefaultSelector", Selector)
    monkeypatch.setattr(live_runner.os, "read", lambda fd, size: reads[fd].pop(0))
    assert live_runner.bounded_process(["synthetic-never-executed"], 1, 64) == (
        0,
        b"bounded output",
        b"",
        None,
    )
