"""SQLite index of bookmarks for fast list/search per workspace."""

from __future__ import annotations

import time
from dataclasses import dataclass

from app import db


@dataclass
class Bookmark:
    id: int
    workspace: str
    url: str
    title: str
    description: str
    relpath: str
    captured_at: int


def insert(
    workspace: str,
    url: str,
    title: str,
    description: str,
    relpath: str,
) -> int:
    now = int(time.time())
    with db.connect() as conn:
        cur = conn.execute(
            "INSERT INTO bookmarks (workspace, url, title, description, relpath, captured_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (workspace, url, title, description, relpath, now),
        )
        return int(cur.lastrowid or 0)


def search(workspace: str, q: str = "", limit: int = 20) -> list[Bookmark]:
    q = (q or "").strip()
    with db.connect() as conn:
        if q:
            pat = f"%{q}%"
            rows = conn.execute(
                "SELECT * FROM bookmarks WHERE workspace = ? AND "
                "(title LIKE ? OR description LIKE ? OR url LIKE ?) "
                "ORDER BY captured_at DESC LIMIT ?",
                (workspace, pat, pat, pat, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM bookmarks WHERE workspace = ? "
                "ORDER BY captured_at DESC LIMIT ?",
                (workspace, limit),
            ).fetchall()
    return [Bookmark(**dict(r)) for r in rows]
