# SPDX-License-Identifier: AGPL-3.0-only
"""Source-contract checks; no launcher, migration, server, runner or model."""

import json
from pathlib import Path

from app.classroom.demo import EXERCISE, POLICY, VERSION, authorization
from app.controls.contracts import Policy
from tests.classroom_offline import deny_external  # noqa: F401


def test_exact_two_learner_binding_matches_authorization_fixture():
    fixture = json.loads(
        (Path(__file__).parent / "fixtures/classroom/authorization.example.json").read_text()
    )
    assert authorization() == fixture
    assert fixture["exercise_versions"] == {EXERCISE: VERSION}
    assert fixture["teaching_policies"][EXERCISE]["policy_id"] == POLICY
    assert len(fixture["subjects"]) == 2


def test_stub_policy_is_finite_and_cannot_admit_code_execution():
    path = Path(__file__).parents[1] / "app/classroom/demo-policy.json"
    policy = Policy.model_validate_json(path.read_text())
    assert policy.input_price == policy.output_price == 0
    for limit in policy.limits():
        assert limit.tokens == 200000 and limit.microunits == limit.runs == limit.wall_ms == 0
    assert all(
        traffic.runner_calls == 0 and traffic.model_calls == 1 for traffic in policy.traffic()
    )
