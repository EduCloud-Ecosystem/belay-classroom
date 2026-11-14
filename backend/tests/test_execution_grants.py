# SPDX-License-Identifier: AGPL-3.0-only
import hashlib
import json
from dataclasses import replace

import pytest
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

from app.auth import Membership, _grant_ref, authorize, execution_grant, recheck_grant
from app.config import settings
from tests.http_auth import configure, token


@pytest.fixture
def grant_boundary(monkeypatch, tmp_path, request):
    member = dict(institution_id="i", class_id="c", learner_id="gh:1", assignments={"echo-1": "v1"})
    if getattr(request, "param", "legacy") == "roster":
        member.update(
            learner_id="47a8ed4608e14957bf74ac18f93655c1",
            learner_id_kind="cairn_roster_v1",
            grant_generation="a45abc18d8ca4ae6a7b32def7048d2ac",
        )
    auth = dict(
        exercise_versions={"echo-1": "v1"}, subjects={"original": [member], "other": [member]}
    )
    path = configure(monkeypatch, tmp_path, auth)
    app = FastAPI()
    captured = []

    @app.post("/grant", dependencies=[Depends(authorize)])
    def capture(request: Request):
        grant = execution_grant(request.state.identity)
        captured.append(grant)
        return grant.model_dump()

    client = TestClient(app)
    response = client.post(
        "/grant",
        json={"exercise_id": "echo-1"},
        headers={"Authorization": "Bearer " + token("original")},
    )
    assert response.status_code == 200
    return captured[0], path, auth


def test_token_free_check_binds_original_subject(grant_boundary):
    grant, path, auth = grant_boundary
    assert recheck_grant(grant).learner_id == "gh:1"
    assert "original" not in grant.model_dump_json()
    assert "Bearer" not in grant.model_dump_json()
    del auth["subjects"]["original"]
    path.write_text(json.dumps(auth))
    with pytest.raises(HTTPException) as error:
        recheck_grant(grant)
    assert error.value.status_code == 404


@pytest.mark.parametrize("change", ["assignment", "deployed_version", "config", "issuer"])
def test_worker_recheck_fails_closed(grant_boundary, monkeypatch, change):
    grant, path, auth = grant_boundary
    if change == "assignment":
        auth["subjects"]["original"][0]["assignments"].clear()
    elif change == "deployed_version":
        auth["exercise_versions"]["echo-1"] = "v2"
    elif change == "issuer":
        monkeypatch.setattr(settings, "auth_issuer", "https://changed.invalid")
    path.write_text("bad JSON" if change == "config" else json.dumps(auth))
    with pytest.raises(HTTPException):
        recheck_grant(grant)


def test_legacy_reference_remains_compatible(grant_boundary):
    grant, _, _ = grant_boundary
    original = json.dumps(
        [
            "belay-execution-grant-v1",
            settings.auth_issuer,
            settings.auth_audience,
            "original",
            "i",
            "c",
            "gh:1",
        ]
    )
    assert grant.grant_ref == hashlib.sha256(original.encode()).hexdigest()


@pytest.mark.parametrize("grant_boundary", ["roster"], indirect=True)
def test_authority_regrant_invalidates_original_execution(grant_boundary):
    grant, path, auth = grant_boundary
    original = recheck_grant(grant)
    members = auth["subjects"].pop("original")
    path.write_text(json.dumps(auth))
    with pytest.raises(HTTPException):
        recheck_grant(grant)
    members[0]["grant_generation"] = "3d7e9b1e9d3e452ab2f405b85b56685c"
    auth["subjects"]["original"] = members
    path.write_text(json.dumps(auth))
    with pytest.raises(HTTPException):
        recheck_grant(grant)
    renewed = execution_grant(
        replace(
            original,
            grant_ref=_grant_ref(
                "original",
                Membership.model_validate(members[0]),
            ),
        )
    )
    assert renewed.grant_ref != grant.grant_ref
    assert recheck_grant(renewed).learner_id == original.learner_id


@pytest.mark.parametrize("grant_boundary", ["roster"], indirect=True)
@pytest.mark.parametrize("generation", [None, "", "a" * 31, "a" * 33, "A" * 32, "a" * 32 + "\n"])
def test_roster_requires_valid_authority_generation(grant_boundary, generation):
    grant, path, auth = grant_boundary
    auth["subjects"]["original"][0]["grant_generation"] = generation
    path.write_text(json.dumps(auth))
    with pytest.raises(HTTPException) as error:
        recheck_grant(grant)
    assert error.value.status_code == 503
