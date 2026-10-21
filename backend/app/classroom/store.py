# SPDX-License-Identifier: AGPL-3.0-only
"""Bounded private workflow, separate from dialogue and research event tables.

Schema creation and cleanup are explicit operator commands. No prompt/code/text
is stored. Required checkpoint presence is independent of optional monitoring.
"""

from __future__ import annotations

import hashlib
import json
import time
import uuid

from fastapi import HTTPException
from sqlalchemy import JSON, Column, Float, Integer, MetaData, String, Table, delete, select
from sqlalchemy.exc import SQLAlchemyError

NOTICE = "info511-private-guidance-v1"
metadata = MetaData()
sessions = Table(
    "classroom_private_v1",
    metadata,
    Column("owner", String(64), primary_key=True),
    Column("revision", Integer, nullable=False),
    Column("expires", Float, nullable=False),
    Column("body", JSON, nullable=False),
)


def unavailable():
    return HTTPException(503, {"code": "classroom_state_unavailable", "kind": "service_error"})


class PrivateStore:
    def __init__(self, engine, now=time.time):
        self.engine, self.now = engine, now

    def key(self, identity, policy):
        raw = [
            identity.storage_id,
            identity.exercise_id,
            identity.exercise_version,
            policy.policy_id,
        ]
        return hashlib.sha256(json.dumps(raw).encode()).hexdigest()

    def _empty(self):
        return {
            "monitor": "off",
            "checkpoint": False,
            "declaration": None,
            "events": [],
            "alerts": {},
            "requests": {},
        }

    def read(self, identity, policy):
        try:
            with self.engine.begin() as conn:
                row = (
                    conn.execute(
                        select(sessions).where(sessions.c.owner == self.key(identity, policy))
                    )
                    .mappings()
                    .first()
                )
                if row is None or row["expires"] <= self.now():
                    return {
                        **self._empty(),
                        "expires_at": None,
                        "revision": row["revision"] if row else 0,
                    }
                return {**row["body"], "expires_at": row["expires"], "revision": row["revision"]}
        except SQLAlchemyError:
            raise unavailable() from None

    def update(
        self,
        identity,
        policy,
        request_id,
        action,
        values=None,
        *,
        observed=False,
        expected_revision=None,
    ):
        values = values or {}
        fingerprint = hashlib.sha256(
            json.dumps([action, values], sort_keys=True).encode()
        ).hexdigest()
        owner, now = self.key(identity, policy), self.now()
        try:
            with self.engine.begin() as conn:
                row = (
                    conn.execute(
                        select(sessions).where(sessions.c.owner == owner).with_for_update()
                    )
                    .mappings()
                    .first()
                )
                expired = row is not None and row["expires"] <= now
                revision = row["revision"] if row else 0
                body = json.loads(json.dumps(row["body"])) if row and not expired else self._empty()
                # Observations cannot create a session or reactivate permission.
                if observed and body["monitor"] != "active":
                    return {
                        **body,
                        "expires_at": row["expires"] if row and not expired else None,
                        "revision": revision,
                    }
                old = body["requests"].get(request_id)
                if old:
                    if old != fingerprint:
                        raise HTTPException(409, {"code": "request_conflict"})
                    return {**body, "expires_at": row["expires"], "revision": revision}
                if expected_revision is not None and expected_revision != revision:
                    raise HTTPException(409, {"code": "workflow_conflict"})
                if action == "revoke":
                    body.update(monitor="revoked", events=[], alerts={}, requests={})
                else:
                    if len(body["requests"]) >= 128:
                        if action in {"pause", "checkpoint", "declaration"}:
                            # Required presence and the stop control cannot be blocked
                            # by optional event capacity. Revision fencing still applies.
                            body["requests"].pop(next(iter(body["requests"])))
                        else:
                            raise HTTPException(
                                409, {"code": "workflow_limit", "kind": "service_error"}
                            )
                    if action in {"enable", "resume"}:
                        if values.get("notice_version") != NOTICE:
                            raise HTTPException(422, {"code": "notice_required"})
                        body["monitor"] = "active"
                    elif action == "pause":
                        body["monitor"] = "paused"
                    elif action == "checkpoint":
                        body["checkpoint"] = (
                            values.get("schema_present") is True
                            and values.get("unit_present") is True
                        )
                    elif action == "declaration":
                        body["declaration"] = values["declaration"]
                    elif action in {"guidance_opened", "challenge", "retry"}:
                        if body["monitor"] != "active":
                            raise HTTPException(409, {"code": "monitor_inactive"})
                        alert = body["alerts"].get(values.get("alert_id"))
                        if alert is None:
                            raise HTTPException(404, {"code": "alert_unavailable"})
                        alert["state"] = action
                    elif not observed:
                        raise HTTPException(422, {"code": "action_invalid"})
                    if body["monitor"] == "active" and action not in {"enable", "resume"}:
                        event = {"id": request_id, "action": action}
                        if observed:
                            event["rule"] = values["rule"]
                            event["kind"] = values["kind"]
                            if action == "tool_denied":
                                body["alerts"][request_id] = {
                                    "rule": values["rule"],
                                    "state": "open",
                                }
                        elif values.get("alert_id"):
                            event["alert_id"] = values["alert_id"]
                        if len(body["events"]) < 64:
                            body["events"].append(event)
                        else:
                            # Stop optional tracking visibly; do not block required
                            # checkpoints/declarations or private challenge state.
                            body["monitor"] = "full"
                body["requests"][request_id] = fingerprint
                expires = row["expires"] if row and not expired else now + policy.retention_seconds
                if row:
                    result = conn.execute(
                        sessions.update()
                        .where(sessions.c.owner == owner, sessions.c.revision == row["revision"])
                        .values(revision=revision + 1, body=body, expires=expires)
                    )
                    if result.rowcount != 1:
                        raise HTTPException(409, {"code": "workflow_conflict"})
                else:
                    conn.execute(
                        sessions.insert().values(
                            owner=owner, revision=1, expires=expires, body=body
                        )
                    )
                return {**body, "expires_at": expires, "revision": revision + 1}
        except SQLAlchemyError:
            raise unavailable() from None

    def observe(self, identity, policy, action, rule, kind, operation_id=None):
        # Deduplicate a trusted logical operation, never a prompt/content fingerprint.
        operation_id = operation_id or uuid.uuid4().hex
        event_id = hashlib.sha256(json.dumps([action, rule, operation_id]).encode()).hexdigest()[
            :32
        ]
        try:
            state = self.update(
                identity, policy, event_id, action, {"rule": rule, "kind": kind}, observed=True
            )
            return {
                "monitor_state": state["monitor"],
                "alert_id": event_id if event_id in state["alerts"] else None,
            }
        except HTTPException:
            # Failure of optional tracking must not grant access or block independent work.
            return {"monitor_state": "unavailable", "alert_id": None}

    def cleanup(self):
        with self.engine.begin() as conn:
            # Clear expired content. Keep the revision fence for the maximum JWT
            # lifetime so a delayed pre-revocation enable cannot recreate permission.
            conn.execute(
                sessions.update().where(sessions.c.expires <= self.now()).values(body=self._empty())
            )
            conn.execute(delete(sessions).where(sessions.c.expires + 900 <= self.now()))


def configured_store():
    from ..store.db import engine

    return PrivateStore(engine)
