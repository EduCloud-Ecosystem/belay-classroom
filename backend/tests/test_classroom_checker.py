# SPDX-License-Identifier: AGPL-3.0-only
"""Instructor-created synthetic cases; no original data, submissions or model calls."""

from pathlib import Path

import pandas as pd
import pytest

from app.packs.datascience import grader
from app.packs.datascience.leak import prose_discloses
from app.packs.datascience.tidy_check import check_tidy
from tests.classroom_offline import deny_external  # noqa: F401

DATA = (
    Path(__file__).parents[1] / "app/packs/datascience/specs/data/info511-inflation-synthetic.csv"
)


def case():
    source = pd.read_csv(DATA)
    # Expected cells expressed independently of a pandas reshaping solution.
    rows = [
        ("Example North", 1993, 1.25),
        ("Example North", 1994, None),
        ("Example North", 1995, -2.5),
        ("Example South", 1993, 0),
        ("Example South", 1994, 3.125),
        ("Example South", 1995, None),
        ("Example West", 1993, None),
        ("Example West", 1994, 4.5),
        ("Example West", 1995, 6),
    ]
    return source, pd.DataFrame(rows, columns=["country", "year", "annual_inflation"])


def test_reordered_cells_pass_and_input_unchanged():
    source, output = case()
    assert check_tidy(source, source.copy(), output.iloc[::-1])[0]


@pytest.mark.parametrize(
    "fault, expected",
    [
        ("drop", "row_count"),
        ("fill", "missingness"),
        ("duplicate", "duplicate_key"),
        ("text_year", "year_type"),
        ("float_year", "year_type"),
        ("value", "source_value"),
        ("key", "keys"),
        ("overwrite", "source_preserved"),
        ("infinite", "numeric_value"),
    ],
)
def test_meaningfully_wrong_results(fault, expected):
    source, output = case()
    preserved = source.copy()
    if fault == "drop":
        output = output.dropna()
    elif fault == "fill":
        output = output.fillna(0)
    elif fault == "duplicate":
        output.iloc[1] = output.iloc[0]
    elif fault == "text_year":
        output["year"] = output["year"].astype(str)
    elif fault == "float_year":
        output["year"] = output["year"].astype(float)
    elif fault == "value":
        output.loc[0, "annual_inflation"] += 0.01
    elif fault == "key":
        output.loc[0, "country"] = "Invented country"
    elif fault == "overwrite":
        preserved.loc[0, "1993"] = 999
    elif fault == "infinite":
        output.loc[0, "annual_inflation"] = float("inf")
    ok, detail = check_tidy(source, preserved, output)
    assert not ok
    assert detail.startswith(expected + ":")


def test_spec_stages_checker_without_original_dataset(monkeypatch):
    from app.core.runner import RunnerResult

    captured = {}

    def fake_runner(source, *, files):
        captured.update(files)
        return RunnerResult(
            ok=True,
            stdout='__GRADE__{"ok":true,"goalMet":false,"checks":[]}',
            stderr="",
            error=None,
            timed_out=False,
            exit_code=0,
            wall_ms=0,
        )

    monkeypatch.setattr(grader.runner, "run_python", fake_runner)
    grader.grade("# instructor-created incomplete attempt", {"id": "info511-lab3-q4-synthetic"})
    assert "tidy_check.py" in captured
    assert not any("country-inflation.csv" in key for key in captured)


def test_assessed_call_blocked_but_documentation_name_allowed():
    exercise = "info511-lab3-q4-synthetic"
    assert prose_discloses("Try `frame.melt(id_vars=['country'])`", exercise)
    assert not prose_discloses(
        "What does the pandas melt documentation say about identifiers?", exercise
    )


def test_csv_serialization_checks_reuse_cell_seam():
    from app.classroom.csv_check import check_csv

    _, output = case()
    assert check_csv(output.iloc[::-1].to_csv(index=False).encode())[0]
    assert not check_csv(output.fillna(0).to_csv(index=False).encode())[0]
    bad = output.copy()
    bad["year"] = bad["year"].astype(float)
    assert check_csv(bad.to_csv(index=False).encode())[1].startswith("year_type:")
    assert not check_csv(b"country,year,annual_inflation\nExample North,1993,NaN\n")[0]


def test_submitted_csv_requests_pinned_blob_without_worktree_execution(monkeypatch, tmp_path):
    from types import SimpleNamespace

    from app.classroom.csv_check import submitted_csv

    revision, blob = "a" * 40, "b" * 40
    content = b"country,year,annual_inflation\nExample North,1993,1.25\n"
    expected = [
        (["cat-file", "-e", revision + "^{commit}"], b""),
        (["rev-parse", "--verify", revision + ":tidy-inflation.csv"], blob.encode()),
        (["cat-file", "-t", blob], b"blob"),
        (["cat-file", "-s", blob], str(len(content)).encode()),
        (["cat-file", "blob", blob], content),
    ]

    def fake_git(command, **kwargs):
        suffix, result = expected.pop(0)
        assert command == ["git", "-C", str(tmp_path), *suffix]
        assert kwargs["timeout"] == 10 and kwargs["check"] is True
        return SimpleNamespace(stdout=result)

    monkeypatch.setattr("app.classroom.csv_check.subprocess.run", fake_git)
    assert submitted_csv(tmp_path, revision, "tidy-inflation.csv") == content
    assert expected == []
    with pytest.raises(ValueError):
        submitted_csv(tmp_path, "HEAD", "tidy-inflation.csv")
