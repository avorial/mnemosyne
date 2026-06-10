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
    """
    CREATE TABLE IF NOT EXISTS asana_workspace_map (
        workspace TEXT PRIMARY KEY,
        asana_workspace_gid TEXT NOT NULL,
        asana_workspace_name TEXT NOT NULL,
        mapped_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS todos (
        gid TEXT PRIMARY KEY,
        workspace TEXT NOT NULL,
        name TEXT NOT NULL,
        completed INTEGER NOT NULL DEFAULT 0,
        due_on TEXT,
        notes TEXT NOT NULL DEFAULT '',
        modified_at TEXT NOT NULL DEFAULT '',
        last_synced_at INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE INDEX IF NOT EXISTS todos_workspace_idx ON todos(workspace)",
    "CREATE INDEX IF NOT EXISTS todos_completed_idx ON todos(completed)",
    """
    CREATE TABLE IF NOT EXISTS capture_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        workspace TEXT NOT NULL,
        kind TEXT NOT NULL,
        summary TEXT NOT NULL,
        created_at INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS capture_log_created_idx ON capture_log(created_at)",
    """
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL
    )
    """,
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
