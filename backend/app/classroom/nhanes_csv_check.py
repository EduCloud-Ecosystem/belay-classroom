# SPDX-License-Identifier: AGPL-3.0-only
"""Immutable submitted-CSV evidence only; no notebook execution or grade writes."""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import subprocess
from pathlib import Path

from ..packs.datascience.nhanes_check import COLUMNS, check_nhanes
from .assignments import EXERCISE, VERSION
from .csv_check import MAX_BYTES, submitted_csv

DATA = Path(__file__).parents[1] / "packs/datascience/specs/data"
SOURCES = {
    "DEMO_L_selected.csv": "4a9c6d40ccbd4cb8a3886b20e2ec506e74c70c8e641347a941b9209f61369587",
    "BPXO_L_selected.csv": "4ae89d264da5da4020fd6e8fdd0171ae188b7ed9191aeb8b18af20b30c1556a9",
}


def check_csv(content: bytes) -> tuple[bool, str]:
    import pandas as pd

    if len(content) > MAX_BYTES:
        return False, "csv_limit: CSV exceeds the 65536-byte rehearsal limit."
    inputs = []
    for name, expected in SOURCES.items():
        raw = (DATA / name).read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected:
            raise ValueError("pinned public source hash changed")
        inputs.append(pd.read_csv(io.BytesIO(raw)))
    try:
        rows = list(csv.reader(io.StringIO(content.decode("utf-8")), strict=True))
    except (UnicodeError, csv.Error):
        return False, "csv_format: provide UTF-8 comma-separated data."
    if not rows or rows[0] != list(COLUMNS):
        return (
            False,
            "columns: provide SEQN, RIDAGEYR, reading, systolic_mm_hg, bpxo_match in that order.",
        )
    values = []
    for row in rows[1:]:
        if len(row) != 5:
            return False, "csv_format: every data row must have exactly five cells."
        seqn, age, reading, value, match = row
        if re.fullmatch(r"[1-9][0-9]{0,15}", seqn) is None:
            return False, "key_type: serialize SEQN as an integer identifier."
        if re.fullmatch(r"[0-9]{1,3}", age) is None:
            return False, "age_value: serialize RIDAGEYR as an integer."
        if reading not in {"1", "2", "3"}:
            return False, "reading_type: represent reading as integer 1, 2 or 3."
        try:
            number = float("nan") if value in {"", "NA"} else float(value)
        except ValueError:
            return False, "numeric_value: use a number, blank or literal NA."
        if value not in {"", "NA"} and not math.isfinite(number):
            return False, "numeric_value: use finite numbers; missing cells are blank or NA."
        values.append((int(seqn), int(age), int(reading), number, match))
    demo, bpxo = inputs
    return check_nhanes(demo, bpxo, demo.copy(), bpxo.copy(), pd.DataFrame(values, columns=rows[0]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--path", default="tidy-nhanes.csv")
    args = parser.parse_args()
    try:
        content = submitted_csv(
            args.repository, args.revision, args.path, expected_name="tidy-nhanes.csv"
        )
        ok, detail = check_csv(content)
        print(
            json.dumps(
                {
                    "kind": "formative_nhanes_csv_check",
                    "ok": ok,
                    "detail": detail,
                    "exercise_id": EXERCISE,
                    "exercise_version": VERSION,
                    "revision": args.revision,
                    "path": args.path,
                    "csv_sha256": hashlib.sha256(content).hexdigest(),
                    "sources_sha256": SOURCES,
                    "notebook_executed": False,
                    "source_preservation_verified": False,
                    "method_verified": False,
                    "grade_approved": False,
                }
            )
        )
        return 0 if ok else 1
    except (ValueError, OSError, subprocess.SubprocessError):
        print(
            json.dumps({"ok": False, "kind": "service_error", "code": "csv_evidence_unavailable"})
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
