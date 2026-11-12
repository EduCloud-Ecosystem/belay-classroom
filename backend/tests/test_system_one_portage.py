# SPDX-License-Identifier: AGPL-3.0-only
"""Actual Belay SDK -> pinned Portage -> synthetic engine, with shadow advice."""

import json

import pytest
from openai import APIStatusError

from app.controls.contracts import ControlError
from app.controls.runtime import operation
from tests.test_portage_integration import CONTROL_SCOPE, invoke
from tests.test_portage_integration import configured as configured
from tests.test_portage_integration import connected as connected

pytestmark = pytest.mark.parametrize("connected", [True], indirect=True)


def reports(portage):
    with portage.db() as db:
        return [json.loads(row[0]) for row in db.execute("SELECT report FROM shadow_decisions")]


def test_actual_sdk_receives_ordinary_response_with_shadow_advice(connected, ledger):  # noqa: F811
    provider, portage, state = connected
    with operation(ledger, CONTROL_SCOPE, "shadow-success"):
        result = provider.json(
            role="planner",
            tier="fast",
            system="Synthetic classroom fixture",
            user="Find evidence for this hypothesis",
            max_tokens=50,
        )
    assert result == {"hint": "check missingness"}
    assert state["gateway_calls"] == state["calls"] == 1
    advice = reports(portage)
    assert len(advice) == 1
    assert advice[0]["decisions"]["recommended_tier"]["value"] == "code_large"
    # The upstream fixture independently asserts it received code_small.
    assert advice[0]["model_forward_calls"] == 0
    assert portage.usage("course01", "learner01")["committed"] == 15


def test_explicit_repair_counts_both_sdk_transports_and_decisions(connected, ledger):  # noqa: F811
    provider, portage, state = connected
    state["repair"] = True
    with operation(ledger, CONTROL_SCOPE, "shadow-repair"):
        assert invoke(provider) == {"hint": "check missingness"}
    assert state["gateway_calls"] == state["calls"] == len(reports(portage)) == 2
    assert portage.usage("course01", "learner01")["committed"] == 30
    assert ledger.summary()["consumed"]["tokens"] == 30


@pytest.mark.parametrize("mode", ["missing_usage", "upstream_error"])
def test_shadow_does_not_settle_unknown_usage_or_retry(connected, ledger, mode):  # noqa: F811
    provider, portage, state = connected
    state["usage"] = False
    state["fail"] = mode == "upstream_error"
    with operation(ledger, CONTROL_SCOPE, "shadow-unknown"):
        if state["fail"]:
            with pytest.raises(APIStatusError):
                invoke(provider)
        else:
            assert invoke(provider) == {"hint": "check missingness"}
    assert state["gateway_calls"] == state["calls"] == len(reports(portage)) == 1
    assert ledger.summary()["states"]["unknown"] == 1
    assert portage.usage("course01", "learner01")["committed"] > 15


@pytest.mark.parametrize("refusal", ["revoked", "exhausted"])
def test_refused_sdk_attempt_creates_no_shadow_or_upstream_work(connected, ledger, refusal):  # noqa: F811
    provider, portage, state = connected
    if refusal == "revoked":
        state["active"] = False
    else:
        portage.member("course01", "learner01", 1)
    with (
        operation(ledger, CONTROL_SCOPE, "shadow-refused"),
        pytest.raises(ControlError if refusal == "revoked" else APIStatusError),
    ):
        invoke(provider)
    assert state["gateway_calls"] == 1 and state["calls"] == 0
    assert reports(portage) == []
