# SPDX-License-Identifier: AGPL-3.0-only
"""Separate one-job live launcher. validate is stdlib-only; run requires an exact grant."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import math
import os
import re
import stat
import sys
import tempfile
import time
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from .assignments import EXERCISE, POLICY, VERSION
from .demo import authorization, bind_learner, check_binding

PROFILE = Path(__file__).with_name("live-profile-v1.json")
BACKEND = Path(__file__).parents[2]


def source_manifest():
    paths = sorted(
        path
        for folder in (BACKEND / "app", BACKEND / "tests")
        for path in folder.rglob("*")
        if path.is_file() and path.suffix in {".py", ".json", ".csv"}
    )
    paths += sorted(BACKEND.glob("requirements*.txt")) + [BACKEND / "pyproject.toml"]
    hashes = {
        str(path.relative_to(BACKEND)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }
    digest = hashlib.sha256(
        json.dumps(hashes, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return digest, hashes


def distribution_versions():
    versions = {"python": sys.version.split()[0]}
    for name in ("openai", "httpx", "httpx2", "fastapi", "SQLAlchemy", "PyJWT", "pandas", "numpy"):
        try:
            versions[name] = version(name)
        except PackageNotFoundError:
            versions[name] = "unavailable"
    return versions


def read_profile():
    profile = json.loads(PROFILE.read_bytes())
    stages = {
        "classifier": {"http_attempts": 1, "output_tokens": 100},
        "planner": {"http_attempts": 2, "output_tokens": 400},
        "reasoner": {"http_attempts": 8, "output_tokens": 800},
        "self_eval": {"http_attempts": 8, "output_tokens": 400},
    }
    if (
        (profile["exercise_id"], profile["exercise_version"], profile["teaching_policy_id"])
        != (EXERCISE, VERSION, POLICY)
        or profile["max_messages_bytes"] != 16384
        or profile["max_attempts"] != 19
        or profile["runner_calls"] != 8
        or profile["total_microunits"] != 350000
        or profile["input_price_microunits_per_token"] != 1
        or profile["output_price_microunits_per_token"] != 1
        or profile["stages"] != stages
        or sum(v["http_attempts"] for v in profile["stages"].values()) != profile["max_attempts"]
        or sum(
            v["http_attempts"] * (profile["max_messages_bytes"] + 1024 + v["output_tokens"])
            for v in profile["stages"].values()
        )
        != profile["aggregate_tokens"]
        or profile["aggregate_tokens"] != 341252
        or profile["aggregate_tokens"] > profile["total_microunits"]
    ):
        raise ValueError("live profile bounds changed")
    return profile


def private_json(path):
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) & 0o077
        or info.st_uid != os.getuid()
    ):
        raise ValueError("owner-only ordinary file required")
    return json.loads(path.read_text())


def read_inputs(grant_path):
    profile, grant = read_profile(), private_json(grant_path)
    if (
        grant.get("profile_sha256") != hashlib.sha256(PROFILE.read_bytes()).hexdigest()
        or grant.get("source_sha256") != source_manifest()[0]
        or grant.get("p1_profile_approved") is not True
        or grant.get("root_execution_authorized") is not True
        or grant.get("runner_admitted") is not True
    ):
        raise ValueError("exact source/profile review, runner admission and root grant required")
    for name, pattern in {
        "p1_review_sha256": r"[0-9a-f]{64}",
        "request_id": r"[A-Za-z0-9_-]{16,64}",
        "deployment_id": r"[A-Za-z0-9_-]{1,64}",
        "reservation_id": r"[A-Za-z0-9_-]{16,128}",
        "runner_admission_evidence": r"[A-Za-z0-9_-]{16,128}",
    }.items():
        if not isinstance(grant.get(name), str) or re.fullmatch(pattern, grant[name]) is None:
            raise ValueError("review and reservation references required")
    review = Path(grant["p1_review_path"])
    if (
        not review.is_absolute()
        or hashlib.sha256(review.read_bytes()).hexdigest() != grant["p1_review_sha256"]
    ):
        raise ValueError("P1 reviewed artifact hash differs")
    if not Path(grant["data_dir"]).is_absolute():
        raise ValueError("absolute dedicated installation path required")
    if any(
        type(grant.get(k)) not in {int, float} or not math.isfinite(grant[k])
        for k in ("not_before", "expires_at")
    ):
        raise ValueError("finite absolute grant timestamps required")
    if not 0 < grant["expires_at"] - grant["not_before"] <= profile["max_window_seconds"]:
        raise ValueError("invalid grant window")
    if (
        type(grant.get("reserved_microunits")) is not int
        or grant["reserved_microunits"] != profile["total_microunits"]
        or grant.get("root_budget_total_microunits") != 20000000
        or type(grant.get("other_held_or_spent_microunits")) is not int
        or grant["other_held_or_spent_microunits"] < 10000
        or grant["other_held_or_spent_microunits"] + profile["total_microunits"] > 20000000
    ):
        raise ValueError("root cumulative reservation required")
    return profile, grant


def read_key(path):
    info = path.lstat()
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) & 0o077
        or info.st_uid != os.getuid()
    ):
        raise ValueError("owner-only named credential file required")
    values = []
    for line in path.read_text().splitlines():
        name, separator, value = line.strip().partition("=")
        if separator and name == "OPENAI_API_KEY":
            values.append(value.strip().strip('"').strip("'"))
    if len(values) != 1 or re.fullmatch(r"[A-Za-z0-9_-]{20,512}", values[0]) is None:
        raise ValueError("one explicit OpenAI credential required")
    return values[0]


def configure(profile, grant, key):
    # A fresh dedicated process: discard inherited model/account/cloud overrides.
    keep = {name: os.environ[name] for name in ("PATH", "LANG", "TMPDIR") if name in os.environ}
    os.environ.clear()
    os.environ.update(keep)
    from .demo import configure_environment

    configure_environment()
    os.environ.update(
        PROVIDER="openai_compatible",
        OPENAI_BASE_URL=profile["base_url"],
        OPENAI_API_KEY=key,
        MODEL_FAST=profile["model"],
        MODEL_STRONG=profile["model"],
        LLM_BILLING_MODE="metered",
        LLM_TIMEOUT_SECONDS=str(profile["http_wall_seconds"]),
        OPENAI_RESPONSE_FORMAT="json_object",
        OPENAI_FINAL_CONTENT_ONLY="1",
        OPENAI_REASONING="1",
        CONTROLS_DEPLOYMENT_ID=grant["deployment_id"],
        CONTROLS_INFERENCE_WINDOW_SECONDS="0",
        CONTROLS_INFERENCE_EXPIRES_AT=str(grant["expires_at"]),
        CONTROLS_INFERENCE_TOTAL_MICROUNITS=str(profile["total_microunits"]),
        DIALOGUE_ENABLED="0",
    )
    for name in ("openai", "httpx", "httpcore", "httpx2", "httpcore2"):
        logging.getLogger(name).setLevel(logging.CRITICAL)


def budget(profile):
    value = json.loads(Path(__file__).with_name("demo-policy.json").read_text())
    value.update(
        version=profile["profile_id"],
        price_version=profile["price_version"],
        input_price=1,
        output_price=1,
        execution_seconds=profile["max_window_seconds"],
    )
    for scope in ("deployment", "institution", "classroom", "learner"):
        value[scope] = {
            "tokens": profile["aggregate_tokens"],
            "microunits": profile["total_microunits"],
            "runs": profile["runner_calls"],
            "wall_ms": profile["runner_wall_ms"],
        }
        value[scope + "_traffic"].update(queue_jobs=1, active_jobs=1, model_calls=1, runner_calls=1)
    return value


def prepare(runtime, directory, profile, grant):
    if directory.exists():
        raise ValueError("new live installation required; never adopt a stub directory")
    with tempfile.TemporaryDirectory(prefix="belay-live-policy-") as temporary:
        policy = Path(temporary) / "policy.json"
        policy.write_text(json.dumps(budget(profile)))
        result = runtime.prepare(directory, policy, 8018, 5188)
    (directory / "authorization.json").write_text(
        json.dumps(authorization(EXERCISE, VERSION, POLICY), indent=2)
    )
    runtime.private_write(directory / "live-grant.json", json.dumps(grant, sort_keys=True).encode())
    manifest = json.loads((directory / "runtime.json").read_text())
    manifest["inference_window"] = {
        "started": grant["not_before"],
        "expires": grant["expires_at"],
        "total_microunits": profile["total_microunits"],
    }
    (directory / "runtime.json").write_text(json.dumps(manifest, indent=2))
    (directory / "attempt-evidence").mkdir(mode=0o700)
    from .store import configured_store, metadata

    metadata.create_all(configured_store().engine)
    return {
        **result,
        "private_schema_initialized": True,
        "retention_seconds": 3600,
        "backups": "prohibited",
    }


def cleanup_private_installation(directory):
    """Explicit dedicated-installation purge; retains accounting and recovery fences.

    Authorization is revoked before deletion. Files and SQL cannot share one
    transaction: if deletion fails, the safer revoked state may remain.
    This is ordinary deletion, with no secure-erasure or backup-removal claim.
    """
    from sqlalchemy import delete, select

    from ..controls.admission import jobs
    from ..controls.contracts import ControlError
    from ..controls.data import data
    from ..controls.jobs_http import execution_store
    from .live_provider import write_evidence
    from .store import configured_store, sessions

    directory = directory.resolve()
    execution, private = execution_store(), configured_store()
    expected = (directory / "belay.sqlite3").resolve()
    for engine in (execution.ledger.engine, private.engine):
        if (
            engine.dialect.name != "sqlite"
            or not engine.url.database
            or Path(engine.url.database).resolve() != expected
        ):
            raise ControlError("live_cleanup_database_mismatch", 503)
    with execution.ledger.transaction() as conn:
        if conn.execute(
            select(jobs.c.id).where(
                jobs.c.state.in_(["queued", "running", "cancel_requested", "unknown"])
            )
        ).first():
            raise ControlError("live_cleanup_active_work", 409)
        authorization_path = directory / "authorization.json"
        auth = private_json(authorization_path)
        if not isinstance(auth.get("subjects"), dict):
            raise ControlError("live_cleanup_authority_unavailable", 503)
        write_evidence(authorization_path, {**auth, "subjects": {}})
        private_rows = conn.execute(delete(sessions)).rowcount
        encrypted_rows = conn.execute(delete(data)).rowcount
    return {
        "cleanup_completed": True,
        "authorization_revoked": True,
        "private_rows_deleted": private_rows,
        "encrypted_rows_deleted": encrypted_rows,
        "accounting_preserved": True,
        "secure_erasure_claimed": False,
    }


def live_adapter(run, store, runner):
    """Shared guarded adapter; the explicit launchers execute it on their main thread."""
    from ..agent import get_llm
    from ..controls.contracts import ControlError
    from ..controls.jobs_worker import AskAdapter
    from ..controls.runtime import attempt_guard, reservation_guard
    from ..core.registry import get_active_pack
    from ..core.runner import execution_backend
    from ..store import ConsentRouter, SqlStore
    from .policy import enforce

    class LiveAdapter(AskAdapter):
        def check(self, job):
            run.authority()
            run.assert_unblocked()
            if job["id"] != run.operation:
                raise ControlError("live_turn_not_granted", 403)
            scope = super().check(job)
            if scope != run.scope:
                raise ControlError("live_turn_not_granted", 403)
            identity, payload = self.store.load(job)
            enforce(identity, payload)
            return scope

        def execute(self, job):
            identity, payload = self.store.load(job)
            with (
                attempt_guard(lambda: enforce(identity, payload)),
                reservation_guard(run.reserve),
                execution_backend(runner),
            ):
                return super().execute(job)

    return LiveAdapter(store, ConsentRouter(SqlStore()), get_active_pack(), get_llm)


def read_turn(turn_path):
    if not turn_path or turn_path.stat().st_size > 8192:
        raise ValueError("bounded synthetic turn file required")
    turn = json.loads(turn_path.read_text())
    if (
        set(turn) != {"message", "source", "schema_present", "unit_present", "declaration"}
        or type(turn["message"]) is not str
        or type(turn["source"]) is not str
        or not turn["message"].strip()
        or turn["schema_present"] is not True
        or turn["unit_present"] is not True
        or turn["declaration"] != "ai_assisted"
    ):
        raise ValueError("explicit synthetic prediction and assistance declaration required")
    return turn


def mark_started(run):
    from .live_provider import write_evidence

    write_evidence(
        run.directory / "run-started.json",
        {
            "operation": run.operation,
            "request_id": run.grant["request_id"],
            "reservation_id": run.grant["reservation_id"],
            "profile_sha256": run.grant["profile_sha256"],
            "source_sha256": run.grant["source_sha256"],
            "started_at": time.time(),
            "expires_at": run.grant["expires_at"],
        },
        new=True,
    )


def run_turn(runtime, directory, profile, grant, grant_path, turn_path, response_output=None):
    from fastapi.testclient import TestClient
    from sqlalchemy import select

    from ..controls.admission import jobs
    from ..controls.contracts import ControlError, Policy
    from ..controls.jobs_http import execution_store
    from ..controls.worker import run_one
    from .live_provider import LiveRun, install, wall_deadline, write_evidence
    from .live_runner import ContainerRunner

    run = LiveRun(profile, grant, directory, grant_path)
    run.authority()
    if (
        response_output is not None
        and response_output.resolve() != directory / "synthetic-released-result.json"
    ):
        raise ValueError("explicit private synthetic result artifact path required")
    check_binding(directory, EXERCISE, VERSION, POLICY)
    turn = read_turn(turn_path)
    store = execution_store()
    with store.ledger.transaction() as conn:
        if (
            store.ledger.policy(conn) != Policy(**budget(profile))
            or conn.execute(select(jobs.c.id)).first()
        ):
            raise ValueError("fresh exact-policy one-job installation required")
    runner = ContainerRunner(run)
    runner.preflight()  # Requires root's cached image; never pulls/builds or calls a model.
    install(run)
    bind_learner(runtime, "bob")
    from ..main import app

    host = runtime.runtime_host(directory, runtime.load(directory))
    client = TestClient(
        app,
        headers={
            "Authorization": "Bearer " + host.token(),
            "X-Belay-Institution": "synthetic-inst",
            "X-Belay-Class": "synthetic-class",
        },
    )

    # Durable one-shot before the first state-changing HTTP request. A crash,
    # rejection or unknown turn cannot be replayed by restarting this command.
    mark_started(run)
    private_path = "/api/classroom/" + EXERCISE + "/" + VERSION
    state = client.get(private_path)
    if state.status_code != 200:
        raise ControlError("live_private_state_unavailable", 503)
    for suffix, body in (
        ("prediction", {"action": "checkpoint", "schema_present": True, "unit_present": True}),
        ("declaration", {"action": "declaration", "declaration": "ai_assisted"}),
    ):
        response = client.post(
            private_path,
            json={
                "request_id": "live_" + suffix + "_00000001",
                "expected_revision": state.json()["revision"],
                **body,
            },
        )
        if response.status_code != 200:
            raise ControlError("live_checkpoint_not_recorded", 503)
        state = response
    body = {
        "request_id": grant["request_id"],
        "participant_id": "edu:2",
        "exercise_id": EXERCISE,
        "exercise_version": VERSION,
        "mode": "study",
        "stance": "peer",
        "event": "chat",
        "source": turn["source"],
        "recent": [{"who": "student", "text": turn["message"]}],
    }
    submitted = client.post("/api/sol/jobs", json=body)
    if submitted.status_code != 202 or submitted.json()["id"] != run.operation:
        raise ControlError("live_job_not_admitted", 503)
    adapter = live_adapter(run, store, runner)
    with wall_deadline(max(0.001, grant["expires_at"] - time.time())):
        run_one(store.admission, adapter)
    run.authority()
    client.headers.update({"Authorization": "Bearer " + host.token()})
    response = client.get("/api/sol/jobs/" + run.operation)
    if response.status_code != 200:
        raise ControlError("live_result_unavailable", 503)
    status = response.json()
    if response_output is not None:
        if status["state"] == "completed":
            write_evidence(
                response_output,
                {
                    "synthetic_only": True,
                    "operation": run.operation,
                    "expires_at": min(time.time() + 300, grant["expires_at"]),
                    "result": status["result"],
                },
                new=True,
            )
    summary = {
        "operation": run.operation,
        "state": status["state"],
        "reason": status.get("reason"),
        "ledger": store.ledger.summary(),
        "reservation_id": grant["reservation_id"],
        "invoice_reconciled": False,
        "result_location": "existing_encrypted_result_store",
        "result_retention_seconds": 300,
        "scripted_synthetic_learner": True,
    }
    write_evidence(directory / "run-result.json", summary, new=True)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["validate", "prepare", "check", "run", "browser", "cleanup"]
    )
    parser.add_argument("--data-dir", type=Path)
    parser.add_argument("--grant", type=Path)
    parser.add_argument(
        "--credentials-file",
        type=Path,
        default=Path("/Users/gregchism/.config/educloud/classroom-pilot/.env"),
    )
    parser.add_argument("--turn", type=Path)
    parser.add_argument("--response-output", type=Path)
    parser.add_argument("--accept-private-retention", action="store_true")
    args = parser.parse_args()
    try:
        profile = read_profile()
        if args.action == "validate":
            from .browser_demo import browser_source_manifest

            digest, files = source_manifest()
            result = {
                "validated_source_only": True,
                "profile_sha256": hashlib.sha256(PROFILE.read_bytes()).hexdigest(),
                "source_sha256": digest,
                "source_files": files,
                "policy": budget(profile),
                "installed_distributions": distribution_versions(),
                "model_calls": 0,
                "grant_checked": False,
                "browser_source_sha256": browser_source_manifest()[0],
            }
            if args.grant:
                read_inputs(args.grant)
                result["grant_checked"] = True
            print(json.dumps(result, sort_keys=True))
            return 0
        if not args.grant or not args.data_dir:
            raise ValueError("exact grant and installation required")
        profile, grant = read_inputs(args.grant.resolve())
        directory = args.data_dir.resolve()
        if directory != Path(grant["data_dir"]).resolve():
            raise ValueError("installation differs from root grant")
        configure(
            profile, grant, read_key(args.credentials_file)
        )  # Before settings/pack/DB/SDK imports.
        from .. import controlled_runtime as runtime

        if args.action == "prepare":
            if not args.accept_private_retention:
                raise ValueError("explicit private retention acceptance required")
            result = prepare(runtime, directory, profile, grant)
        else:
            runtime.load(directory)
            if private_json(directory / "live-grant.json") != grant:
                raise ValueError("installed grant immutable; restart cannot renew it")
            with runtime.lock_directory(directory):
                if args.action == "cleanup":
                    result = cleanup_private_installation(directory)
                    (directory / "synthetic-released-result.json").unlink(missing_ok=True)
                elif args.action == "check":
                    check_binding(directory, EXERCISE, VERSION, POLICY)
                    result = runtime.check(directory)
                elif args.action == "browser":
                    from .browser_demo import start

                    result = start(
                        runtime, directory, profile, grant, args.grant.resolve(), args.turn
                    )
                else:
                    result = run_turn(
                        runtime,
                        directory,
                        profile,
                        grant,
                        args.grant.resolve(),
                        args.turn,
                        args.response_output,
                    )
        print(
            json.dumps(
                {**result, "lane": "live_one_turn", "profile": profile["profile_id"]},
                sort_keys=True,
            )
        )
        return 0 if args.action != "run" or result.get("state") == "completed" else 1
    except Exception as exc:
        # Only trusted codes, never exception messages or SDK bodies/URLs/headers.
        code = getattr(exc, "code", None)
        if not isinstance(code, str) or re.fullmatch(r"[a-z_]{1,64}", code) is None:
            code = "live_classroom_not_admitted"
        print(json.dumps({"error": code, "action": args.action}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
