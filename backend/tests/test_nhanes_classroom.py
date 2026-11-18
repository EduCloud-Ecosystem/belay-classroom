# SPDX-License-Identifier: AGPL-3.0-only
"""Public teaching data, instructor-created faults and no external execution."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pandas as pd
import pytest

from app.classroom.assignments import NHANES
from app.classroom.demo import authorization
from app.classroom.live_runner import checked_inputs, checked_verdict
from app.classroom.nhanes_csv_check import SOURCES, check_csv
from app.controls.contracts import ControlError
from app.packs.datascience import grader, misconceptions
from app.packs.datascience._harness import _run_check
from app.packs.datascience.nhanes_check import COLUMNS, READINGS, SUCCESS, check_nhanes
from tests.classroom_offline import deny_external  # noqa: F401

ROOT = Path(__file__).parents[1] / "app/packs/datascience"


def test_missing_record_hint_gives_one_source_lookup_only_in_the_nhanes_exercise():
    move_id = "DS-nhanes-blank-record"
    moves = misconceptions.for_exercise("info511-nhanes-wrangling")["misconceptions"]
    move = next(m["peer_move"] for m in moves if m["id"] == move_id)
    assert "one blank reading" in move and "SEQN" in move and "original BPXO" in move
    assert not any(answer in move for answer in ("no_BPXO_record", ".merge(", ".isin(", "192"))
    assert all(
        m["id"] != move_id for m in misconceptions.for_exercise("ds-foundations")["misconceptions"]
    )


def case():
    demo = pd.read_csv(ROOT / "specs/data/DEMO_L_selected.csv")
    bpxo = pd.read_csv(ROOT / "specs/data/BPXO_L_selected.csv")
    # Independent keyed expansion; no merge/melt implementation is copied here.
    observations = {row[0]: row[1:] for row in bpxo.itertuples(index=False, name=None)}
    rows = []
    for seqn, age in demo.itertuples(index=False, name=None):
        values = observations.get(seqn, (None, None, None))
        for number, value in enumerate(values, 1):
            rows.append(
                (seqn, age, number, value, "matched" if seqn in observations else "no_BPXO_record")
            )
    return demo, bpxo, pd.DataFrame(rows, columns=COLUMNS)


def test_frozen_public_extracts_keys_and_missingness_are_not_inflation_expectations():
    for name, expected in SOURCES.items():
        assert hashlib.sha256((ROOT / "specs/data" / name).read_bytes()).hexdigest() == expected
    demo, bpxo, out = case()
    assert (len(demo), len(bpxo), len(out)) == (64, 56, 192)
    assert not demo.SEQN.duplicated().any() and not bpxo.SEQN.duplicated().any()
    assert set(bpxo.SEQN).issubset(demo.SEQN)
    assert out.systolic_mm_hg.isna().sum() == 58
    assert out[out.bpxo_match == "matched"].systolic_mm_hg.isna().sum() == 34
    assert out[out.bpxo_match == "no_BPXO_record"].systolic_mm_hg.isna().sum() == 24
    assert out.groupby("reading").systolic_mm_hg.apply(lambda x: x.isna().sum()).tolist() == [
        16,
        18,
        24,
    ]
    assert (out.systolic_mm_hg == 0).sum() == 0
    assert check_nhanes(demo, bpxo, demo.copy(), bpxo.copy(), out.iloc[::-1]) == (True, SUCCESS)
    assert list(bpxo.columns) == ["SEQN", *READINGS]


@pytest.mark.parametrize(
    "fault,code",
    [
        ("inner_join", "row_count"),
        ("drop_missing", "row_count"),
        ("fill_zero", "missingness"),
        ("duplicate", "duplicate_key"),
        ("unknown_key", "keys"),
        ("text_reading", "reading_type"),
        ("float_identifier", "key_type"),
        ("changed_age", "age_value"),
        ("invented_match", "component_match"),
        ("altered_value", "source_value"),
        ("infinity", "numeric_value"),
        ("overwrite_demo", "source_preserved"),
        ("overwrite_bpxo", "source_preserved"),
        ("extra_column", "columns"),
    ],
)
def test_survey_wrangle_faults_are_rejected_without_model_judgment(fault, code):
    demo, bpxo, out = case()
    preserved_demo, preserved_bpxo = demo.copy(), bpxo.copy()
    observed = out.systolic_mm_hg.first_valid_index()
    if fault == "inner_join":
        out = out[out.bpxo_match == "matched"]
    elif fault == "drop_missing":
        out = out.dropna()
    elif fault == "fill_zero":
        out = out.fillna(0)
    elif fault == "duplicate":
        out.iloc[1] = out.iloc[0]
    elif fault == "unknown_key":
        out.loc[0, "SEQN"] = 999999
    elif fault == "text_reading":
        out["reading"] = out.reading.astype(str)
    elif fault == "float_identifier":
        out["SEQN"] = out.SEQN.astype(float)
    elif fault == "changed_age":
        out.loc[0, "RIDAGEYR"] += 1
    elif fault == "invented_match":
        out.loc[0, "bpxo_match"] = "no_exam_attendance"
    elif fault == "altered_value":
        out.loc[observed, "systolic_mm_hg"] += 1
    elif fault == "infinity":
        out.loc[observed, "systolic_mm_hg"] = float("inf")
    elif fault == "overwrite_demo":
        preserved_demo.loc[0, "RIDAGEYR"] += 1
    elif fault == "overwrite_bpxo":
        preserved_bpxo.loc[0, "BPXOSY1"] = 999
    elif fault == "extra_column":
        out["clinical_label"] = "invented"
    ok, detail = check_nhanes(demo, bpxo, preserved_demo, preserved_bpxo, out)
    assert not ok and detail.startswith(code + ":")


def test_missing_bpxo_record_is_not_the_same_as_three_missing_readings():
    demo, bpxo, out = case()
    all_missing = bpxo[bpxo[list(READINGS)].isna().all(axis=1)].SEQN
    assert len(all_missing) == 8
    assert set(out[out.SEQN.isin(all_missing)].bpxo_match) == {"matched"}
    out.loc[out.SEQN.isin(all_missing), "bpxo_match"] = "no_BPXO_record"
    assert check_nhanes(demo, bpxo, demo.copy(), bpxo.copy(), out)[1].startswith("component_match:")


def test_csv_cannot_establish_notebook_execution_but_checks_same_keyed_values():
    demo, bpxo, out = case()
    content = out.to_csv(index=False).encode()
    assert check_csv(content) == (True, SUCCESS)
    assert check_csv(content.replace(b",,", b",0,"))[0] is False
    assert check_csv(content.replace(b",,", b",NaN,"))[0] is False
    assert check_csv(b"x" * 65537)[1].startswith("csv_limit:")
    assert check_csv(content + b"not,a,five,column,row,extra\n")[1].startswith("csv_format:")


def test_method_check_is_syntactic_and_semantic_check_uses_frozen_sources():
    demo, bpxo, out = case()
    spec = grader.load_spec(NHANES[0])["checks"][0]
    ns = {"demographics": demo.copy(), "bp_readings": bpxo.copy(), "tidy_nhanes": out}
    references = {spec["demographics_file"]: demo, spec["bpxo_file"]: bpxo}
    assert not _run_check(spec, ns, "", references, "x.melt()", None, check_nhanes)[0]
    assert _run_check(spec, ns, "", references, "x.merge(); x.melt()", None, check_nhanes) == (
        True,
        None,
        SUCCESS,
    )


def test_live_inputs_pin_both_raw_extracts_checker_spec_and_assignment():
    spec = grader.load_spec(NHANES[0])
    files = grader._stage_data(spec)
    files.update(
        {
            "student.py": "# instructor-created control, not executed",
            "spec.json": json.dumps(spec),
            "nhanes_check.py": (ROOT / "nhanes_check.py").read_text(),
        }
    )
    limits = {"input_files": 6, "input_bytes": 262144}
    assert len(checked_inputs(grader._harness_source(), files, None, limits, NHANES[0])) == 6
    altered = dict(files)
    altered["data/BPXO_L_selected.csv"] += "\n"
    with pytest.raises(ControlError):
        checked_inputs(grader._harness_source(), altered, None, limits, NHANES[0])
    with pytest.raises(ControlError):
        checked_inputs(grader._harness_source(), files, None, limits)


def test_live_nhanes_verdict_rejects_legacy_and_unbounded_checker_text():
    value = {
        "ok": True,
        "goalMet": True,
        "metric": None,
        "stdout": "",
        "error": None,
        "checks": [{"type": "nhanes_participant_readings", "ok": True, "detail": SUCCESS}],
    }
    assert checked_verdict("__GRADE__" + json.dumps(value), NHANES[0])["goal_met"]
    with pytest.raises(ControlError):
        checked_verdict("__GRADE__" + json.dumps(value))
    value["checks"][0]["detail"] = "a model says you passed"
    with pytest.raises(ControlError):
        checked_verdict("__GRADE__" + json.dumps(value), NHANES[0])


def test_new_assignment_requires_explicit_authorization_and_errors_remain_learning_feedback(
    monkeypatch,
):
    from app.classroom import policy

    exercise, version, policy_id = NHANES
    auth = authorization(*NHANES)
    assert auth["exercise_versions"] == {exercise: version}
    with pytest.raises(ValueError):
        authorization("arbitrary", version, policy_id)
    selected = NS(**auth["teaching_policies"][exercise])
    identity = NS(
        exercise_id=exercise, exercise_version=version, assignments=((exercise, version),)
    )
    monkeypatch.setattr(
        policy,
        "_configuration",
        lambda: (
            None,
            NS(teaching_policies={exercise: selected}, exercise_versions={exercise: version}),
        ),
    )
    assert policy.policy_for(identity) is selected
    captured = []
    monkeypatch.setattr(
        policy,
        "configured_store",
        lambda: NS(observe=lambda *args: captured.append(args) or {"monitor_state": "off"}),
    )
    policy.record_check(identity, {"ok": True, "goalMet": False})
    assert captured[0][3:] == ("check_needs_attention", "learning_feedback")
