# SPDX-License-Identifier: AGPL-3.0-only
"""Native Cairn export -> signed Belay identity -> actual SDK and Portage gateway."""

import pytest
from fastapi import HTTPException

from app.auth import execution_grant, recheck_grant
from app.config import settings
from app.controls.contracts import Scope
from app.controls.runtime import operation
from tests.test_enrollment_authority import edge as edge
from tests.test_enrollment_authority import install, native_documents, request
from tests.test_portage_integration import configured as base_configured  # noqa: F401
from tests.test_portage_integration import connected as connected
from tests.test_portage_integration import invoke


@pytest.fixture
def configured(monkeypatch, request):
    request.getfixturevalue("base_configured")
    monkeypatch.setattr(settings, "portage_institution", "institution")
    monkeypatch.setattr(settings, "portage_classroom", "course")


def test_native_enrollment_to_portage_and_revocation(edge, connected, ledger):  # noqa: F811
    snapshots = native_documents()
    provider, portage, state = connected
    install(edge, snapshots["active"])
    assert request(edge).status_code == 200
    identity = edge[4][-1]
    grant = execution_grant(identity)
    portage.member("course01", identity.learner_id, 100000)
    scope = Scope("test", identity.institution_id, identity.class_id, identity.learner_id)
    with operation(ledger, scope, "native-active", guard=lambda: recheck_grant(grant)):
        assert invoke(provider) == {"hint": "check missingness"}
    assert state["gateway_calls"] == state["calls"] == 1
    assert set(state["authority_paths"]) == {"/internal/member/" + identity.learner_id}
    assert portage.usage("course01", identity.learner_id)["committed"] == 15
    install(edge, snapshots["revoked"])
    with operation(ledger, scope, "native-revoked", guard=lambda: recheck_grant(grant)):
        with pytest.raises(HTTPException):
            invoke(provider)
    assert state["gateway_calls"] == state["calls"] == 1
    install(edge, snapshots["active"])
    with operation(ledger, scope, "native-replayed", guard=lambda: recheck_grant(grant)):
        with pytest.raises(HTTPException):
            invoke(provider)
    assert state["gateway_calls"] == state["calls"] == 1
    install(edge, snapshots["renewed"])
    assert request(edge).status_code == 200
    renewed = execution_grant(edge[4][-1])
    with operation(ledger, scope, "native-renewed", guard=lambda: recheck_grant(renewed)):
        assert invoke(provider) == {"hint": "check missingness"}
    assert state["gateway_calls"] == state["calls"] == 2
    assert portage.usage("course01", identity.learner_id)["committed"] == 30
