# SPDX-License-Identifier: AGPL-3.0-only
"""Trusted teaching policy at HTTP and queued execution boundaries."""

from __future__ import annotations

from fastapi import HTTPException

from ..auth import _configuration, denied, execution_grant, recheck_grant
from ..controls.runtime import attempt_guard
from .assignments import SUPPORTED
from .store import configured_store

EXERCISE = "info511-lab3-q4-synthetic"


def policy_for(identity):
    # Only the two explicitly registered teaching fixtures use these controls.
    if identity.exercise_id not in {item[0] for item in SUPPORTED}:
        return None
    _, authorization = _configuration()
    policy = authorization.teaching_policies.get(identity.exercise_id)
    if policy is None:
        raise HTTPException(503, {"code": "teaching_policy_unavailable", "kind": "service_error"})
    if (
        authorization.exercise_versions.get(identity.exercise_id) != identity.exercise_version
        or dict(identity.assignments).get(identity.exercise_id) != identity.exercise_version
    ):
        raise denied()
    if policy.exercise_version != identity.exercise_version:
        raise HTTPException(503, {"code": "teaching_policy_unavailable", "kind": "service_error"})
    return policy


def enforce(identity, payload, *, observe=False, trusted_support=False, operation_id=None):
    policy = policy_for(identity)
    if policy is None:
        return
    recheck_grant(execution_grant(identity))
    if payload.get("stance", "peer") != "peer" or payload.get("mode", "study") != "study":
        observation = (
            configured_store().observe(
                identity,
                policy,
                "tool_denied",
                "hints_only",
                "policy_guidance",
                operation_id=operation_id or payload.get("request_id"),
            )
            if observe
            else {}
        )
        raise HTTPException(
            403,
            {
                "code": "hints_only",
                "kind": "policy_guidance",
                "policy_id": policy.policy_id,
                "message": "This assignment permits hints and debugging questions. Choose study/peer and retry; your work is unchanged.",
                **observation,
            },
        )
    # Reuse the existing explicit distress floor without storing its content.
    # Only worker-owned encrypted input may set trusted_support.
    from ..agent.distress import extra_terms, has_distress_signal
    from ..agent.orchestrator import _latest_student_message
    from ..config import settings

    latest = payload.get("message") or _latest_student_message(payload.get("recent", []))
    if trusted_support or (
        settings.distress_routing_enabled and has_distress_signal(latest, extra_terms(settings))
    ):
        return
    if not configured_store().read(identity, policy)["checkpoint"]:
        raise HTTPException(
            409,
            {
                "code": "prediction_required",
                "kind": "completion_reminder",
                "message": "Write your predicted schema and observational unit in your notebook, then record that checkpoint before asking for hints.",
            },
        )

    if observe:
        configured_store().observe(
            identity,
            policy,
            "tool_allowed",
            "hints_only",
            "workflow_action",
            operation_id=operation_id or payload.get("request_id"),
        )


class GuardedProvider:
    def __init__(self, identity, payload, provider):
        self.identity, self.payload, self.provider = identity, payload, provider
        self.name = getattr(provider, "name", "classroom")

    def json(self, **kwargs):
        enforce(self.identity, self.payload)
        with attempt_guard(lambda: enforce(self.identity, self.payload)):
            return self.provider.json(**kwargs)


def guard_provider(identity, payload, provider):
    return GuardedProvider(identity, payload, provider) if policy_for(identity) else provider


def record_check(identity, result):
    try:
        policy = policy_for(identity)
    except HTTPException:
        return {"monitor_state": "unavailable", "alert_id": None}
    if policy is None:
        return None
    # Caller supplies pack.run result, never the client's claimed result or a model guess.
    if not result.get("ok"):
        kind, rule = "service_error", "execution_unavailable"
        if (result.get("pack") or {}).get("execution_status") == "student_error":
            kind, rule = "learning_feedback", "code_error"
    else:
        kind = "learning_feedback"
        rule = "check_passed" if result.get("goalMet") else "check_needs_attention"
    return configured_store().observe(identity, policy, "checker_result", rule, kind)


def guarded_turn(identity, payload, tutor, provider, store):
    """Cover secondary safety providers too; never replace the controls ledger."""
    if policy_for(identity) is None:
        return tutor(payload, provider, store)
    with attempt_guard(lambda: enforce(identity, payload)):
        return tutor(payload, provider, store)
