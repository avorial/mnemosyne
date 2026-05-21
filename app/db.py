import sqlite3
from contextlib import contextmanager
from typing import Iterator

from app.config import config

SCHEMA = [
    """
    CREATE TABLE IF NOT EXISTS magic_links (
        token TEXT PRIMARY KEY,
        email TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        used_at INTEGER
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS sessions (
        token TEXT PRIMARY KEY,
        email TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        expires_at INTEGER NOT NULL,
        last_used_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS layouts (
        workspace TEXT PRIMARY KEY,
        layout_json TEXT NOT NULL,
        updated_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS bookmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace TEXT NOT NULL,
        url TEXT NOT NULL,
        title TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        relpath TEXT NOT NULL,
        captured_at INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS bookmarks_workspace_idx ON bookmarks(workspace)",
    "CREATE INDEX IF NOT EXISTS bookmarks_captured_at_idx ON bookmarks(captured_at)",
]


def init() -> None:
    config.db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect() as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        for stmt in SCHEMA:
            conn.execute(stmt)


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(str(config.db_path), isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
    finally:
        conn.close()
