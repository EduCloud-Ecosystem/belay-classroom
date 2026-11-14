# SPDX-License-Identifier: AGPL-3.0-only
"""Verified bearer identity + operator-owned authorization, shared by both HTTP edges."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Self

import jwt
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .authority_state import Authority
from .authority_state import check as check_authority
from .config import settings


class Membership(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    institution_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    class_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,64}$")
    learner_id: str = Field(max_length=64)
    # Only trusted authorization can select this namespace. A matching format
    # does not prove Cairn provenance or current enrollment; the operator must
    # supply the existing roster row, never derive it from a login or name.
    learner_id_kind: Literal["host_numeric_v1", "cairn_roster_v1"] = "host_numeric_v1"
    grant_generation: str | None = None
    assignments: dict[str, str]

    @model_validator(mode="after")
    def validate_learner_id(self) -> Self:
        pattern = (
            r"[0-9a-f]{32}"
            if self.learner_id_kind == "cairn_roster_v1"
            else r"[a-z][a-z0-9_]*:[0-9]+"
        )
        if not re.fullmatch(pattern, self.learner_id):
            raise ValueError("learner label does not match its configured namespace")
        if self.learner_id_kind == "cairn_roster_v1":
            if self.grant_generation is None or not re.fullmatch(
                r"[0-9a-f]{32}", self.grant_generation
            ):
                raise ValueError("roster grants require an authority-supplied generation")
        elif self.grant_generation is not None:
            raise ValueError("legacy grants do not support generation fencing")
        return self


class TeachingPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    exercise_version: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,64}$")
    policy_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    mode: Literal["hints_only"]
    retention_seconds: int = Field(ge=60, le=86400)


class Authorization(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    # Operator binds each exercise in the installed pack to its deployed version.
    exercise_versions: dict[str, str]
    subjects: dict[str, list[Membership]]
    teaching_policies: dict[str, TeachingPolicy] = Field(default_factory=dict)
    authority: Authority | None = None


@dataclass(frozen=True)
class Identity:
    institution_id: str
    class_id: str
    learner_id: str
    assignments: tuple[tuple[str, str], ...]
    exercise_id: str = ""
    exercise_version: str = ""
    active_assignments: tuple[tuple[str, str], ...] = ()
    grant_ref: str = ""

    @property
    def storage_id(self) -> str:
        # Domain separation excludes all pre-auth legacy keys (no inferred ownership).
        raw = json.dumps(["belay-identity-v1", self.institution_id, self.class_id, self.learner_id])
        return hashlib.sha256(raw.encode()).hexdigest()

    def exercise_key(self, exercise_id: str, version: str) -> str:
        raw = json.dumps(["belay-assignment-v1", exercise_id, version])
        return hashlib.sha256(raw.encode()).hexdigest()


def denied() -> HTTPException:
    # Same response for missing membership, forged identity and nonexistent resources.
    return HTTPException(404, "resource unavailable")


_bearer = HTTPBearer(auto_error=False)


async def authorize(
    request: Request, credentials: HTTPAuthorizationCredentials | None = Depends(_bearer)
) -> Identity:
    """Authenticate before parsing learner payloads or invoking a pack/model/store.

    Local/test environments still use signed credentials; there is no anonymous mode.
    Only these explicitly selected environments allow a non-HTTPS issuer.
    Authorization is re-read per request so revocation does not wait for token expiry.
    """
    key, authorization = _configuration()

    token = credentials.credentials if credentials is not None else ""
    if not token or len(token) > 16384:
        raise HTTPException(401, "invalid credentials", headers={"WWW-Authenticate": "Bearer"})
    try:
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            issuer=settings.auth_issuer,
            audience=settings.auth_audience,
            options={"require": ["iss", "aud", "exp", "iat", "sub"]},
        )
        if any(type(claims[k]) is not int for k in ("exp", "iat", "nbf") if k in claims):
            raise ValueError
        if not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", claims["sub"]):
            raise ValueError
        if not 0 < claims["exp"] - claims["iat"] <= 900:
            raise ValueError
    except (jwt.PyJWTError, ValueError, TypeError, OverflowError):
        raise HTTPException(
            401, "invalid credentials", headers={"WWW-Authenticate": "Bearer"}
        ) from None

    members = authorization.subjects.get(claims["sub"], [])
    institution = request.headers.get("x-belay-institution")
    class_id = request.headers.get("x-belay-class")
    if institution is not None or class_id is not None:
        members = [m for m in members if m.institution_id == institution and m.class_id == class_id]
    if len(members) != 1:
        raise denied()
    m = members[0]
    payload = {}
    if request.method in {"POST", "PUT", "PATCH"}:
        try:
            payload = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise HTTPException(422, "invalid JSON") from None
        if not isinstance(payload, dict):
            raise HTTPException(422, "object required")
    for field, expected in (
        ("pseudo_id", m.learner_id),
        ("participant_id", m.learner_id),
        ("anon_code", m.learner_id),
        ("learner_id", m.learner_id),
        ("institution_id", m.institution_id),
        ("class_id", m.class_id),
    ):
        if field in payload and payload[field] != expected:
            raise denied()
    if "pid" in request.path_params and request.path_params["pid"] != m.learner_id:
        raise denied()
    ex = payload.get("exercise_id", "")
    version = ""
    if ex:
        if not isinstance(ex, str):
            raise denied()
        version = authorization.exercise_versions.get(ex, "")
        if not version or m.assignments.get(ex) != version:
            raise denied()
        if "exercise_version" in payload and payload["exercise_version"] != version:
            raise denied()
    elif "exercise_id" in payload or "exercise_version" in payload:
        raise denied()
    # Apply the established PII boundary to /api as well as the sidecar.
    from .integrations.quad.pii import PIIRejected, assert_no_pii

    try:
        assert_no_pii(payload)
    except PIIRejected:
        raise HTTPException(422, "PII rejected at boundary") from None
    identity = Identity(
        m.institution_id,
        m.class_id,
        m.learner_id,
        tuple(m.assignments.items()),
        ex,
        version,
        tuple(
            (ex_id, ver)
            for ex_id, ver in m.assignments.items()
            if authorization.exercise_versions.get(ex_id) == ver
        ),
    )
    identity = Identity(**{**identity.__dict__, "grant_ref": _grant_ref(claims["sub"], m)})
    request.state.identity = identity
    return identity


def _configuration() -> tuple[str, Authorization]:
    if settings.belay_env not in {"production", "local", "test"}:
        raise HTTPException(503, "authentication not configured")
    try:
        if not all(
            (
                settings.auth_issuer,
                settings.auth_audience,
                settings.auth_public_key_file,
                settings.auth_authorization_file,
            )
        ):
            raise ValueError
        if settings.belay_env == "production" and not settings.auth_issuer.startswith("https://"):
            raise ValueError
        key = Path(settings.auth_public_key_file).read_text(encoding="utf-8")
        authorization = Authorization.model_validate_json(
            Path(settings.auth_authorization_file).read_text(encoding="utf-8")
        )
        # Validate the operator's versions, including empty/malformed entries.
        opaque = re.compile(r"^[A-Za-z0-9_.:-]{1,64}$")
        if any(
            not opaque.fullmatch(ex) or not opaque.fullmatch(version)
            for ex, version in authorization.exercise_versions.items()
        ):
            raise ValueError
        if any(
            not opaque.fullmatch(ex)
            or authorization.exercise_versions.get(ex) != p.exercise_version
            for ex, p in authorization.teaching_policies.items()
        ):
            raise ValueError
        if any(not re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", sub) for sub in authorization.subjects):
            raise ValueError
        for members in authorization.subjects.values():
            scopes = [(m.institution_id, m.class_id) for m in members]
            if len(scopes) != len(set(scopes)):
                raise ValueError
            if any(
                not opaque.fullmatch(ex) or not opaque.fullmatch(v)
                for m in members
                for ex, v in m.assignments.items()
            ):
                raise ValueError
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
        from cryptography.hazmat.primitives.serialization import load_pem_public_key

        public_key = load_pem_public_key(key.encode())
        if not isinstance(public_key, RSAPublicKey) or public_key.key_size < 2048:
            raise ValueError
        if settings.auth_authority_state_file or authorization.authority is not None:
            if not settings.auth_authority_state_file or authorization.authority is None:
                raise ValueError
            if any(
                m.learner_id_kind != "cairn_roster_v1"
                for members in authorization.subjects.values()
                for m in members
            ):
                raise ValueError
            check_authority(
                settings.auth_authority_state_file,
                authorization.authority,
                authorization.model_dump(),
                settings.auth_issuer,
                settings.auth_audience,
            )
    except (OSError, ValueError, TypeError, sqlite3.Error):
        raise HTTPException(503, "authentication not configured") from None

    return key, authorization


class ExecutionGrant(BaseModel):
    """Opaque reference to the ORIGINAL verified principal, never a bearer token."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    grant_ref: str = Field(pattern=r"^[0-9a-f]{64}$")
    institution_id: str
    class_id: str
    learner_id: str
    exercise_id: str
    exercise_version: str


def _grant_ref(subject: str, member: Membership) -> str:
    binding: list[str | None] = [
        "belay-execution-grant-v1",
        settings.auth_issuer,
        settings.auth_audience,
        subject,
        member.institution_id,
        member.class_id,
        member.learner_id,
    ]
    # Preserve every legacy reference. New roster grants bind the authority's
    # generation so a renewal cannot sustain work admitted by the old grant.
    # The authority must not reuse a generation or roll back its snapshots.
    if member.learner_id_kind == "cairn_roster_v1":
        binding.extend(["cairn-roster-grant-v1", member.grant_generation])
    raw = json.dumps(binding)
    return hashlib.sha256(raw.encode()).hexdigest()


def execution_grant(identity: Identity) -> ExecutionGrant:
    if not identity.exercise_id or not identity.exercise_version:
        raise denied()
    return ExecutionGrant(**{k: getattr(identity, k) for k in ExecutionGrant.model_fields})


def recheck_grant(grant: ExecutionGrant) -> Identity:
    """Re-read current authorization without saving or replaying a login token.

    A different subject with identical learner scope cannot sustain this grant.
    Key/config failure, original membership revocation or version change fail closed.
    """
    _, authorization = _configuration()
    for subject, members in authorization.subjects.items():
        for m in members:
            if _grant_ref(subject, m) != grant.grant_ref:
                continue
            if (m.institution_id, m.class_id, m.learner_id) != (
                grant.institution_id,
                grant.class_id,
                grant.learner_id,
            ):
                raise denied()
            if (
                authorization.exercise_versions.get(grant.exercise_id) != grant.exercise_version
                or m.assignments.get(grant.exercise_id) != grant.exercise_version
            ):
                raise denied()
            return Identity(
                m.institution_id,
                m.class_id,
                m.learner_id,
                tuple(m.assignments.items()),
                grant.exercise_id,
                grant.exercise_version,
                tuple(
                    (ex, v)
                    for ex, v in m.assignments.items()
                    if authorization.exercise_versions.get(ex) == v
                ),
                grant.grant_ref,
            )
    raise denied()
