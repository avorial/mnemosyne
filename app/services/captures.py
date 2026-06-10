"""Capture log — a glanceable record that today's captures actually landed.

Every successful capture (note, inbox drop, bookmark, todo, phone share)
writes one row. The Captured widget reads today's rows back. This is a
trust surface, not an archive: reading the content stays Obsidian's job.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

from app import db
from app.services.calendar_types import local_tz

MAX_SUMMARY = 80


@dataclass(frozen=True)
class Capture:
    kind: str        # note | inbox | bookmark | todo | share
    summary: str
    at: datetime     # local tz


def log(workspace: str, kind: str, summary: str) -> None:
    summary = " ".join((summary or "").split())
    if len(summary) > MAX_SUMMARY:
        summary = summary[: MAX_SUMMARY - 1] + "…"
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO capture_log (workspace, kind, summary, created_at) VALUES (?, ?, ?, ?)",
            (workspace, kind, summary, int(time.time())),
        )


def today(workspace: str, limit: int = 10) -> tuple[int, list[Capture]]:
    """(total today, newest-first rows up to limit) for one workspace."""
    tz = local_tz()
    midnight = int(datetime.combine(datetime.now(tz).date(), datetime.min.time(), tzinfo=tz).timestamp())
    with db.connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) AS n FROM capture_log WHERE workspace = ? AND created_at >= ?",
            (workspace, midnight),
        ).fetchone()["n"]
        rows = conn.execute(
            "SELECT kind, summary, created_at FROM capture_log "
            "WHERE workspace = ? AND created_at >= ? ORDER BY created_at DESC LIMIT ?",
            (workspace, midnight, limit),
        ).fetchall()
    return total, [
        Capture(
            kind=r["kind"],
            summary=r["summary"],
            at=datetime.fromtimestamp(r["created_at"], tz),
        )
        for r in rows
    ]
