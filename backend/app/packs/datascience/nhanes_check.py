# SPDX-License-Identifier: AGPL-3.0-only
"""Formative NHANES join/reshape check; no diagnosis, inference or grade writes."""

from __future__ import annotations

import math
from numbers import Integral, Real

COLUMNS = ("SEQN", "RIDAGEYR", "reading", "systolic_mm_hg", "bpxo_match")
READINGS = ("BPXOSY1", "BPXOSY2", "BPXOSY3")
SUCCESS = "All selected participant/reading keys, source values and missingness retained."
FAILURES = frozenset(
    {
        "source_preserved: keep demographics and bp_readings unchanged.",
        "columns: provide SEQN, RIDAGEYR, reading, systolic_mm_hg, bpxo_match in that order.",
        "row_count: retain three readings for every selected demographic participant, including missing cells.",
        "key_type: keep SEQN as an integer identifier.",
        "reading_type: represent reading as integer 1, 2 or 3.",
        "duplicate_key: each SEQN/reading pair must occur once.",
        "keys: retain exactly the selected participant/reading pairs.",
        "age_value: retain each participant's recorded RIDAGEYR.",
        "component_match: distinguish matched BPXO records from no_BPXO_record.",
        "missingness: retain missing readings as missing; do not drop, fill or invent codes.",
        "numeric_value: retain finite measured values in mm Hg.",
        "source_value: at least one reading differs from its source value.",
        "method: use the assignment's explicit merge() and melt() operations.",
    }
)


def check_nhanes(
    original_demo, original_bpxo, preserved_demo, preserved_bpxo, result
) -> tuple[bool, str]:
    import pandas as pd

    if (
        not isinstance(original_demo, pd.DataFrame)
        or not isinstance(original_bpxo, pd.DataFrame)
        or list(original_demo.columns) != ["SEQN", "RIDAGEYR"]
        or list(original_bpxo.columns) != ["SEQN", *READINGS]
        or original_demo.empty
        or original_demo["SEQN"].isna().any()
        or original_demo["SEQN"].duplicated().any()
        or original_bpxo["SEQN"].isna().any()
        or original_bpxo["SEQN"].duplicated().any()
        or not set(original_bpxo["SEQN"]).issubset(original_demo["SEQN"])
    ):
        raise ValueError("invalid pinned instructor sources")
    if (
        not isinstance(preserved_demo, pd.DataFrame)
        or not isinstance(preserved_bpxo, pd.DataFrame)
        or not original_demo.equals(preserved_demo)
        or not original_bpxo.equals(preserved_bpxo)
    ):
        return False, "source_preserved: keep demographics and bp_readings unchanged."
    if not isinstance(result, pd.DataFrame) or list(result.columns) != list(COLUMNS):
        return (
            False,
            "columns: provide SEQN, RIDAGEYR, reading, systolic_mm_hg, bpxo_match in that order.",
        )
    component = {row[0]: row[1:] for row in original_bpxo.itertuples(index=False, name=None)}
    expected = {}
    for seqn, age in original_demo.itertuples(index=False, name=None):
        values = component.get(seqn, (float("nan"),) * 3)
        status = "matched" if seqn in component else "no_BPXO_record"
        for reading, value in enumerate(values, 1):
            expected[(int(seqn), reading)] = (age, value, status)
    if len(result) != len(expected):
        return (
            False,
            "row_count: retain three readings for every selected demographic participant, including missing cells.",
        )
    seen: set[tuple[int, int]] = set()
    for seqn, age, reading, value, status in result.itertuples(index=False, name=None):
        if isinstance(seqn, bool) or not isinstance(seqn, Integral):
            return False, "key_type: keep SEQN as an integer identifier."
        if (
            isinstance(reading, bool)
            or not isinstance(reading, Integral)
            or reading not in (1, 2, 3)
        ):
            return False, "reading_type: represent reading as integer 1, 2 or 3."
        key = (int(seqn), int(reading))
        if key in seen:
            return False, "duplicate_key: each SEQN/reading pair must occur once."
        if key not in expected:
            return False, "keys: retain exactly the selected participant/reading pairs."
        seen.add(key)
        expected_age, expected_value, expected_status = expected[key]
        if isinstance(age, bool) or not isinstance(age, Integral) or age != expected_age:
            return False, "age_value: retain each participant's recorded RIDAGEYR."
        if not isinstance(status, str) or status != expected_status:
            return False, "component_match: distinguish matched BPXO records from no_BPXO_record."
        missing, wanted_missing = bool(pd.isna(value)), bool(pd.isna(expected_value))
        if missing != wanted_missing:
            return (
                False,
                "missingness: retain missing readings as missing; do not drop, fill or invent codes.",
            )
        if not missing:
            if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
                return False, "numeric_value: retain finite measured values in mm Hg."
            if not math.isclose(float(value), float(expected_value), rel_tol=0, abs_tol=1e-9):
                return False, "source_value: at least one reading differs from its source value."
    return True, SUCCESS
