# SPDX-License-Identifier: AGPL-3.0-only
"""Learner-only private guidance; no staff/export route and no model calls."""

from dataclasses import replace
from types import SimpleNamespace
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from ..auth import authorize, denied
from ..conversations.bounds import bounded_route
from .policy import policy_for
from .store import NOTICE, configured_store


class Action(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{16,64}$")
    expected_revision: int = Field(ge=0)
    action: Literal[
        "enable",
        "pause",
        "resume",
        "revoke",
        "checkpoint",
        "declaration",
        "guidance_opened",
        "challenge",
        "retry",
    ]
    notice_version: Literal["info511-private-guidance-v1"] | None = None
    schema_present: bool | None = None
    unit_present: bool | None = None
    declaration: Literal["no_ai", "ai_assisted"] | None = None
    alert_id: str | None = Field(default=None, pattern=r"^[0-9a-f]{32}$")


def build_router(prefix):
    api = APIRouter(
        prefix=prefix + "/classroom",
        dependencies=[Depends(authorize)],
        route_class=bounded_route(lambda: SimpleNamespace(max_body_bytes=4096)),
    )

    def context(request, exercise_id, exercise_version):
        identity = request.state.identity
        if (exercise_id, exercise_version) not in identity.active_assignments:
            raise denied()
        identity = replace(identity, exercise_id=exercise_id, exercise_version=exercise_version)
        policy = policy_for(identity)
        if policy is None:
            raise denied()
        return identity, policy

    def public(state, policy, response):
        response.headers["Cache-Control"] = "no-store"
        response.headers["Vary"] = "Authorization, X-Belay-Institution, X-Belay-Class"
        return {k: v for k, v in state.items() if k != "requests"} | {
            "notice_version": NOTICE,
            "policy_id": policy.policy_id,
            "retention_seconds": policy.retention_seconds,
            "notice": "Optional private tracking records tool decisions, checker outcomes and explicit guidance actions only. This interface exposes it only to you; service operators retain necessary database access. Pause stops optional events; revoke removes them. Required access, usage controls and checkpoint/declaration presence remain active. No research consent, grade effect or instructor feed. Records expire from session creation; this rehearsal requires no backups and scheduled cleanup.",
            "declaration_reminder": state["declaration"] is None,
            "presence_only": True,
            "guidance": {
                "hints_only": "Use hints and debugging questions in study/peer mode. Your notebook is unchanged. A challenge records your disagreement privately; it does not override the assignment rule. Retry records your intended next step; submit the permitted Ask separately."
            },
        }

    @api.get("/{exercise_id}/{exercise_version}")
    def get(request: Request, response: Response, exercise_id: str, exercise_version: str):
        identity, policy = context(request, exercise_id, exercise_version)
        return public(configured_store().read(identity, policy), policy, response)

    @api.post("/{exercise_id}/{exercise_version}")
    def act(
        request: Request, response: Response, exercise_id: str, exercise_version: str, body: Action
    ):
        identity, policy = context(request, exercise_id, exercise_version)
        values = body.model_dump(
            exclude={"request_id", "action", "expected_revision"}, exclude_none=True
        )
        fields = {
            "enable": {"notice_version"},
            "resume": {"notice_version"},
            "checkpoint": {"schema_present", "unit_present"},
            "declaration": {"declaration"},
            "guidance_opened": {"alert_id"},
            "challenge": {"alert_id"},
            "retry": {"alert_id"},
            "pause": set(),
            "revoke": set(),
        }
        if set(values) != fields[body.action]:
            raise HTTPException(422, {"code": "action_fields_invalid"})
        state = configured_store().update(
            identity,
            policy,
            body.request_id,
            body.action,
            values,
            expected_revision=body.expected_revision,
        )
        return public(state, policy, response)

    return api
