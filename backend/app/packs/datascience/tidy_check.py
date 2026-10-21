# SPDX-License-Identifier: AGPL-3.0-only
"""Cell-preserving formative check; no model, reference solution or grade writes."""

from __future__ import annotations

import math
from numbers import Integral, Real


def check_tidy(original, preserved, result) -> tuple[bool, str]:
    import pandas as pd

    if not isinstance(preserved, pd.DataFrame) or not original.equals(preserved):
        return False, "source_preserved: keep country_inflation unchanged."
    if not isinstance(result, pd.DataFrame) or list(result.columns) != [
        "country",
        "year",
        "annual_inflation",
    ]:
        return False, "columns: provide country, year, annual_inflation in that order."
    if original.columns[0] != "country" or original["country"].duplicated().any():
        raise ValueError("invalid instructor source")
    expected = {}
    for row in original.itertuples(index=False, name=None):
        for year, value in zip(original.columns[1:], row[1:], strict=True):
            expected[(row[0], int(year))] = value
    if len(result) != len(expected):
        return (
            False,
            "row_count: retain one row for every source country/year cell, including missing cells.",
        )
    seen = set()
    for country, year, value in result.itertuples(index=False, name=None):
        if isinstance(year, bool) or not isinstance(year, Integral):
            return False, "year_type: represent each year as an integer, not text or a float."
        if not isinstance(country, str) or not 1000 <= year <= 9999:
            return False, "keys: retain the source country names and four-digit years."
        key = (country, int(year))
        if key in seen:
            return False, "duplicate_key: each country/year pair must occur once."
        if key not in expected:
            return False, "keys: retain exactly the source country/year pairs."
        seen.add(key)
        want = expected[key]
        missing, wanted_missing = bool(pd.isna(value)), bool(pd.isna(want))
        if missing != wanted_missing:
            return False, "missingness: retain missing cells as missing; do not drop or fill them."
        if not missing:
            if isinstance(value, bool) or not isinstance(value, Real) or not math.isfinite(value):
                return False, "numeric_value: retain finite numeric inflation values."
            if not math.isclose(float(value), float(want), rel_tol=0, abs_tol=1e-9):
                return False, "source_value: at least one value differs from its source cell."
    return True, "All source cells, keys and missingness retained (row order ignored)."
