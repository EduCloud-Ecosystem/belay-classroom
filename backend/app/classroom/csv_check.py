# SPDX-License-Identifier: AGPL-3.0-only
"""Operator-only formative CSV check at an immutable submitted Git revision.

Reads data, never executes a notebook, writes a grade, or confirms a receipt.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import math
import re
import subprocess
from pathlib import Path, PurePosixPath

from ..packs.datascience.tidy_check import check_tidy

SOURCE = Path(__file__).parents[1] / "packs/datascience/specs/data/info511-inflation-synthetic.csv"
SOURCE_SHA256 = "c638d29069c47efbd4589e80fcf959088809f0b0275942f13a1866fc2703ea7b"
MAX_BYTES = 65536


def check_csv(content: bytes) -> tuple[bool, str]:
    import pandas as pd

    if len(content) > MAX_BYTES:
        return False, "csv_limit: CSV exceeds the 65536-byte rehearsal limit."
    source_bytes = SOURCE.read_bytes()
    if hashlib.sha256(source_bytes).hexdigest() != SOURCE_SHA256:
        raise ValueError("synthetic source hash changed")
    try:
        rows = list(csv.reader(io.StringIO(content.decode("utf-8")), strict=True))
    except (UnicodeError, csv.Error):
        return False, "csv_format: provide UTF-8 comma-separated data."
    if not rows or rows[0] != ["country", "year", "annual_inflation"]:
        return False, "columns: provide country, year, annual_inflation in that order."
    values = []
    for row in rows[1:]:
        if len(row) != 3:
            return False, "csv_format: every data row must have exactly three cells."
        country, year, value = row
        if re.fullmatch(r"[1-9][0-9]{3}", year) is None:
            return False, "year_type: serialize each year as four integer digits."
        try:
            number = float("nan") if value in {"", "NA"} else float(value)
        except ValueError:
            return False, "numeric_value: use a number, blank or literal NA."
        # Only blank/NA represent missingness. NaN/Inf spellings are not accepted.
        if value not in {"", "NA"} and not math.isfinite(number):
            return False, "numeric_value: use finite numbers; missing cells are blank or NA."
        values.append((country, int(year), number))
    source = pd.read_csv(io.BytesIO(source_bytes))
    return check_tidy(source, source.copy(), pd.DataFrame(values, columns=rows[0]))


def submitted_csv(repository: Path, revision: str, path: str) -> bytes:
    if re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        raise ValueError("full immutable commit revision required")
    relative = PurePosixPath(path)
    if relative.is_absolute() or ".." in relative.parts or relative.name != "tidy-inflation.csv":
        raise ValueError("explicit relative tidy-inflation.csv path required")

    def git(*args: str) -> bytes:
        return subprocess.run(
            ["git", "-C", str(repository), *args], capture_output=True, check=True, timeout=10
        ).stdout

    git("cat-file", "-e", revision + "^{commit}")
    blob = git("rev-parse", "--verify", revision + ":" + path).decode().strip()
    if re.fullmatch(r"[0-9a-f]{40}", blob) is None:
        raise ValueError("invalid CSV blob")
    if git("cat-file", "-t", blob).strip() != b"blob":
        raise ValueError("CSV must be a regular Git blob")
    if int(git("cat-file", "-s", blob)) > MAX_BYTES:
        raise ValueError("CSV exceeds rehearsal bound")
    return git("cat-file", "blob", blob)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", type=Path, required=True)
    parser.add_argument("--revision", required=True)
    parser.add_argument("--path", default="tidy-inflation.csv")
    args = parser.parse_args()
    try:
        content = submitted_csv(args.repository, args.revision, args.path)
        ok, detail = check_csv(content)
        print(
            json.dumps(
                {
                    "kind": "formative_csv_cell_check",
                    "ok": ok,
                    "detail": detail,
                    "exercise_id": "info511-lab3-q4-synthetic",
                    "exercise_version": "info511-lab3-q4-synthetic-v1",
                    "revision": args.revision,
                    "path": args.path,
                    "csv_sha256": hashlib.sha256(content).hexdigest(),
                    "source_sha256": SOURCE_SHA256,
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
