# SPDX-License-Identifier: AGPL-3.0-only
"""Finite operator snapshots, with a durable rollback watermark (not a roster)."""

import argparse
import hashlib
import json
import os
import re
import sqlite3
import stat
import time
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Authority(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    schema_version: Literal[1]
    authority_id: str = Field(pattern=r"^[0-9a-f]{32}$", max_length=32)
    issuer: str
    audience: str
    revision: int = Field(ge=1, le=2**53 - 1)
    issued_at: int
    expires_at: int


def initialize(path: str, authority_id: str) -> None:
    """Explicit, exclusive initialization. Lost state must never auto-bootstrap."""
    if not re.fullmatch(r"[0-9a-f]{32}", authority_id):
        raise ValueError("invalid authority ID")
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    os.close(fd)
    with sqlite3.connect(path) as db:
        db.execute(
            "CREATE TABLE watermark (id INTEGER PRIMARY KEY CHECK(id=1), "
            "authority_id TEXT NOT NULL, revision INTEGER NOT NULL, digest TEXT NOT NULL, "
            "observed_at INTEGER NOT NULL)"
        )
        db.execute("INSERT INTO watermark VALUES (1, ?, 0, '', 0)", (authority_id,))


def check(path: str, authority: Authority, document: dict, issuer: str, audience: str) -> None:
    now = int(time.time())
    if (
        authority.issuer != issuer
        or authority.audience != audience
        or not authority.issued_at <= now < authority.expires_at
        or not 0 < authority.expires_at - authority.issued_at <= 300
    ):
        raise ValueError("authority unavailable")
    info = os.lstat(path)
    if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o077:
        raise ValueError("private watermark required")
    digest = hashlib.sha256(
        json.dumps(document, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    # mode=rw cannot recreate missing state. One transaction serializes processes.
    db = sqlite3.connect(Path(path).resolve().as_uri() + "?mode=rw", uri=True, timeout=1)
    try:
        db.execute("BEGIN IMMEDIATE")
        row = db.execute(
            "SELECT authority_id, revision, digest, observed_at FROM watermark WHERE id=1"
        ).fetchone()
        if (
            row is None
            or row[0] != authority.authority_id
            or authority.revision < row[1]
            or (authority.revision == row[1] and digest != row[2])
            or now < row[3]
        ):
            raise ValueError("authority rollback or conflict")
        db.execute(
            "UPDATE watermark SET revision=?, digest=?, observed_at=? WHERE id=1",
            (authority.revision, digest, now),
        )
        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Initialize private enrollment rollback state once"
    )
    parser.add_argument("path")
    parser.add_argument("authority_id")
    args = parser.parse_args()
    initialize(args.path, args.authority_id)
