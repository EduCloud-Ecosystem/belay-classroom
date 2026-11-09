# SPDX-License-Identifier: AGPL-3.0-only
"""Finite enrollment through signed HTTP identity and actual worker authorization."""

import copy
import json
import os
import time
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.auth import Identity, authorize, execution_grant, recheck_grant
from app.authority_state import initialize
from app.config import settings
from tests.http_auth import AUDIENCE, ISSUER, configure, token

AUTHORITY = "a45abc18d8ca4ae6a7b32def7048d2ac"
ROSTER = "47a8ed4608e14957bf74ac18f93655c1"


def document():
    now = int(time.time())
    return {
        "authority": {
            "schema_version": 1,
            "authority_id": AUTHORITY,
            "issuer": ISSUER,
            "audience": AUDIENCE,
            "revision": 1,
            "issued_at": now,
            "expires_at": now + 120,
        },
        "exercise_versions": {"echo-1": "v1"},
        "subjects": {
            "verified-subject": [
                {
                    "institution_id": "institution",
                    "class_id": "course",
                    "learner_id": ROSTER,
                    "learner_id_kind": "cairn_roster_v1",
                    "grant_generation": "3d7e9b1e9d3e452ab2f405b85b56685c",
                    "assignments": {"echo-1": "v1"},
                }
            ]
        },
    }


@pytest.fixture
def edge(monkeypatch, tmp_path):
    data = document()
    path = configure(monkeypatch, tmp_path, data)
    state = tmp_path / "watermark.sqlite"
    initialize(str(state), AUTHORITY)
    monkeypatch.setattr(settings, "auth_authority_state_file", str(state))
    app = FastAPI()
    identities = []

    @app.post("/work")
    def work(identity: Identity = Depends(authorize)):
        identities.append(identity)
        return {"learner_id": identity.learner_id}

    client = TestClient(app, headers={"Authorization": "Bearer " + token("verified-subject")})
    return client, path, state, data, identities


def request(edge):
    return edge[0].post("/work", json={"participant_id": ROSTER, "exercise_id": "echo-1"})


def install(edge, value):
    edge[1].write_text(json.dumps(value))


def test_active_refresh_and_process_restart(edge):
    assert request(edge).status_code == 200
    grant = execution_grant(edge[4][-1])
    data = edge[3]
    data["authority"]["revision"] += 1
    install(edge, data)
    assert request(edge).status_code == 200
    assert recheck_grant(grant).learner_id == ROSTER
    # Each call opens a new SQLite connection: no in-memory watermark dependence.
    data["authority"]["revision"] = 1
    install(edge, data)
    assert request(edge).status_code == 503
    with pytest.raises(HTTPException):
        recheck_grant(grant)


@pytest.mark.parametrize(
    "change",
    [
        "expired",
        "future",
        "too-long",
        "wrong-issuer",
        "wrong-audience",
        "wrong-authority",
        "same-revision-conflict",
        "missing-state",
        "corrupt-state",
        "public-state",
        "symlink-state",
        "downgrade",
        "clock-rollback",
        "legacy-member",
        "boolean-revision",
        "unknown-schema",
    ],
)
def test_fail_closed(edge, monkeypatch, change):
    assert request(edge).status_code == 200
    grant = execution_grant(edge[4][-1])
    data = edge[3]
    authority = data["authority"]
    if change != "same-revision-conflict":
        authority["revision"] += 1
    if change == "expired":
        monkeypatch.setattr("app.authority_state.time.time", lambda: authority["expires_at"])
    elif change == "future":
        authority["issued_at"] += 1
    elif change == "too-long":
        authority["expires_at"] = authority["issued_at"] + 301
    elif change == "wrong-issuer":
        authority["issuer"] = "https://other.invalid"
    elif change == "wrong-audience":
        authority["audience"] = "other"
    elif change == "wrong-authority":
        authority["authority_id"] = "95bc972abaec499498b84ddcf38ae8fa"
    elif change == "same-revision-conflict":
        authority["expires_at"] += 1
    elif change == "missing-state":
        edge[2].unlink()
    elif change == "corrupt-state":
        edge[2].write_text("corrupt")
    elif change == "public-state":
        edge[2].chmod(0o644)
    elif change == "symlink-state":
        old = edge[2].with_suffix(".old")
        edge[2].rename(old)
        edge[2].symlink_to(old)
    elif change == "downgrade":
        del data["authority"]
    elif change == "clock-rollback":
        # Still inside validity, but earlier than the last accepted observation.
        monkeypatch.setattr("app.authority_state.time.time", lambda: authority["issued_at"] + 10)
        assert request(edge).status_code == 200
        monkeypatch.setattr("app.authority_state.time.time", lambda: authority["issued_at"] + 5)
    elif change == "legacy-member":
        member = data["subjects"]["verified-subject"][0]
        member.update(learner_id="edu:2", learner_id_kind="host_numeric_v1", grant_generation=None)
        authority["revision"] += 1
    elif change == "boolean-revision":
        authority["revision"] = True
    else:
        authority["schema_version"] = 2
    install(edge, data)
    assert request(edge).status_code == 503
    with pytest.raises(HTTPException):
        recheck_grant(grant)


def test_init_never_overwrites_history(edge):
    with pytest.raises(FileExistsError):
        initialize(str(edge[2]), AUTHORITY)


def test_snapshot_requires_enabled_durable_guard(edge, monkeypatch):
    monkeypatch.setattr(settings, "auth_authority_state_file", "")
    assert request(edge).status_code == 503


def test_revoked_snapshot_blocks_old_and_new_work(edge):
    assert request(edge).status_code == 200
    original = execution_grant(edge[4][-1])
    data = copy.deepcopy(edge[3])
    data["authority"]["revision"] += 1
    data["subjects"] = {}
    install(edge, data)
    assert request(edge).status_code == 404
    with pytest.raises(HTTPException):
        recheck_grant(original)
    install(edge, edge[3])
    assert request(edge).status_code == 503


def native_documents():
    root = os.environ.get("CAIRN_ENROLLMENT_FIXTURES")
    if not root:
        pytest.skip("native Cairn exporter fixtures not configured")
    return {
        name: json.loads((Path(root) / (name + ".json")).read_text())
        for name in ("active", "refresh", "revoked", "renewed", "stale-assignment")
    }


def test_native_cairn_export_through_signed_http_and_worker(edge):
    snapshots = native_documents()
    install(edge, snapshots["active"])
    assert request(edge).status_code == 200
    original = execution_grant(edge[4][-1])
    install(edge, snapshots["refresh"])
    assert request(edge).status_code == 200
    assert recheck_grant(original).learner_id == ROSTER
    install(edge, snapshots["revoked"])
    assert request(edge).status_code == 404
    with pytest.raises(HTTPException):
        recheck_grant(original)
    install(edge, snapshots["active"])
    assert request(edge).status_code == 503
    install(edge, snapshots["renewed"])
    assert request(edge).status_code == 200
    renewed = execution_grant(edge[4][-1])
    assert renewed.grant_ref != original.grant_ref
    with pytest.raises(HTTPException):
        recheck_grant(original)
    assert recheck_grant(renewed).learner_id == ROSTER
    install(edge, snapshots["stale-assignment"])
    assert request(edge).status_code == 404
    with pytest.raises(HTTPException):
        recheck_grant(renewed)
