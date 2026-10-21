# SPDX-License-Identifier: AGPL-3.0-only
"""Explicit synthetic hint-card adapter over the existing controlled launcher.

No external inference. prepare/migrate-private/start are separate operator actions.
Use one learner at a time; stop before switching, retaining the same isolated DB.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path

EXERCISE = "info511-lab3-q4-synthetic"
VERSION = "info511-lab3-q4-synthetic-v1"
POLICY = "info511-hints-v1"
LEARNERS = {"alice": ("synthetic-one", "edu:1"), "bob": ("synthetic-two", "edu:2")}


def authorization():
    assignments = {EXERCISE: VERSION}
    return {
        "exercise_versions": assignments,
        "teaching_policies": {
            EXERCISE: {
                "exercise_version": VERSION,
                "policy_id": POLICY,
                "mode": "hints_only",
                "retention_seconds": 3600,
            }
        },
        "subjects": {
            subject: [
                {
                    "institution_id": "synthetic-inst",
                    "class_id": "synthetic-class",
                    "learner_id": learner,
                    "assignments": assignments,
                }
            ]
            for subject, learner in LEARNERS.values()
        },
    }


def configure_environment():
    # Only this explicitly invoked process: no .env load, real key or endpoint.
    for key in tuple(os.environ):
        if key.startswith(
            (
                "AUTH_",
                "CONTROLS_",
                "DIALOGUE_",
                "OPENAI_",
                "ANTHROPIC_",
                "BEDROCK_",
                "DISTRESS_",
                "INJECTION_",
            )
        ) or key in {"LLM_API_KEY", "DATABASE_URL"}:
            del os.environ[key]
    os.environ.update(
        PROVIDER="local_stub",
        TUTOR_PACK="datascience",
        LLM_BILLING_MODE="unmetered",
        OPENAI_API_KEY="",
        ANTHROPIC_API_KEY="",
        OPENAI_BASE_URL="http://127.0.0.1:1/v1",
        CONTROLS_DEPLOYMENT_ID="info511-synthetic-hint-card-v1",
        DIALOGUE_ENABLED="1",
        DIALOGUE_POLICY_ID="synthetic-hour-no-backups-v1",
        DIALOGUE_RETENTION_SECONDS="3600",
        DIALOGUE_BACKUP_MAX_AGE_SECONDS="3600",
        CLASSROOM_CLEANUP_ENABLED="1",
        MAX_REFINE="1",
        MAX_ESCALATE="1",
        MAX_WORKED_EXAMPLE_RETRY="1",
        INJECTION_GUARD_ENABLED="1",
        DISTRESS_ROUTING_ENABLED="1",
        DISTRESS_TRACE_ENABLED="0",
        DISTRESS_SUPPORT_MESSAGE="This is a synthetic rehearsal. Pause the exercise and ask the supervising operator for support.",
        DISTRESS_ESCALATION_TARGET="Synthetic rehearsal operator; no automatic contact",
    )


def install_hint_card():
    from ..agent import llm
    from ..controls.local_demo import DemoProvider

    class HintCardProvider(DemoProvider):
        name = "local_stub"

        def json(self, **kwargs):
            # Keep the existing model_call accounting seam for EVERY synthetic stage.
            result = super().json(**kwargs)
            if kwargs["role"] == "reasoner":
                result["message"] = (
                    "[Prepared hint card — no model evaluation] "
                    "Describe what one output row represents. Which source columns identify "
                    "that observation, and how will you check that missing cells were retained?"
                )
                result["check_question"] = None
            return result

    llm._PROVIDERS["local_stub"] = HintCardProvider


def bind_learner(runtime, learner):
    import jwt

    from ..controlled_runtime import RuntimeHost

    original = runtime.runtime_host
    subject, learner_id = LEARNERS[learner]

    class ClassroomHost(RuntimeHost):
        def token(self):
            now = int(time.time())
            return jwt.encode(
                {
                    "iss": self.issuer,
                    "aud": runtime.AUDIENCE,
                    "sub": subject,
                    "iat": now,
                    "exp": now + 300,
                },
                self.key,
                algorithm="RS256",
            )

        def bootstrap(self):
            return (
                super()
                .bootstrap()
                .replace(b"'gh:12345'", json.dumps(learner_id).encode())
                .replace(b"'local-demo'", b"'synthetic-inst'")
                .replace(b"'local-class'", b"'synthetic-class'")
            )

    def factory(directory, manifest):
        host = original(directory, manifest)
        # Reuse key loading and same-origin token handler; no key/token is printed.
        selected = object.__new__(ClassroomHost)
        selected.__dict__.update(host.__dict__)
        return selected

    runtime.runtime_host = factory


def check_binding(directory):
    from sqlalchemy import inspect

    from ..auth import _configuration
    from ..store.db import engine

    auth = json.loads((directory / "authorization.json").read_text())
    if (
        auth.get("exercise_versions") != {EXERCISE: VERSION}
        or auth.get("teaching_policies") != authorization()["teaching_policies"]
    ):
        raise ValueError("classroom binding differs")
    # Allow membership removal during the revocation demonstration, never additions.
    expected = authorization()["subjects"]
    if set(auth.get("subjects", {})) - set(expected) or any(
        value not in ([], expected[name]) for name, value in auth.get("subjects", {}).items()
    ):
        raise ValueError("unexpected synthetic subject grants")
    _configuration()
    if not inspect(engine).has_table("classroom_private_v1"):
        raise ValueError("explicit migrate-private required")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=["prepare", "migrate-private", "check", "start", "stop", "cleanup"]
    )
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--learner", choices=LEARNERS, default="alice")
    parser.add_argument("--api-port", type=int, default=8016)
    parser.add_argument("--frontend-port", type=int, default=5186)
    parser.add_argument("--accept-private-retention", action="store_true")
    args = parser.parse_args()
    configure_environment()  # Must precede config, pack and DB imports.
    from .. import controlled_runtime as runtime

    directory = args.data_dir.resolve()
    try:
        if args.action == "prepare":
            policy = Path(__file__).with_name("demo-policy.json")
            result = runtime.prepare(directory, policy, args.api_port, args.frontend_port)
            # prepare is new-directory-only and has never opened a listener.
            (directory / "authorization.json").write_text(json.dumps(authorization(), indent=2))
            result.update(classroom_bound=True, private_schema_initialized=False)
        elif args.action == "stop":
            result = runtime.stop(directory)
        else:
            runtime.load(directory)
            if args.action == "migrate-private":
                if not args.accept_private_retention:
                    raise ValueError("explicit retention acceptance required")
                from ..classroom.store import configured_store, metadata

                with runtime.lock_directory(directory):
                    metadata.create_all(configured_store().engine)
                result = {
                    "private_schema_initialized": True,
                    "retention_seconds": 3600,
                    "backups": "prohibited",
                }
            elif args.action == "cleanup":
                from ..classroom.store import configured_store

                configured_store().cleanup()
                result = {"expired_private_content_cleared": True}
            else:
                check_binding(directory)
                install_hint_card()
                bind_learner(runtime, args.learner)
                result = (
                    runtime.check(directory) if args.action == "check" else runtime.start(directory)
                )
        print(
            json.dumps(
                {**result, "lane": "synthetic_hint_card", "approved_model_evaluation": False}
            )
        )
        return 1 if args.action == "check" and not result.get("start_allowed", True) else 0
    except Exception:
        # No secrets, CSV content or arbitrary provider/DB errors in logs.
        print(json.dumps({"error": "classroom_demo_unavailable", "action": args.action}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
