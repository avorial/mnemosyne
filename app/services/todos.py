"""Todos service — local cache of Asana tasks per Mnemosyne workspace.

Authoritative source is Asana. SQLite is a mirror. Writes go to Asana first,
then to SQLite. Background poll (worker/sync.py) reconciles changes made
elsewhere.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from app import db
from app.services import asana_client

log = logging.getLogger("mnemosyne.todos")


@dataclass
class WorkspaceMapping:
    workspace: str
    asana_workspace_gid: str
    asana_workspace_name: str


@dataclass
class Todo:
    gid: str
    workspace: str
    name: str
    completed: bool
    due_on: str | None
    notes: str
    modified_at: str
    last_synced_at: int


# ---- workspace mapping ----


def get_mapping(workspace: str) -> WorkspaceMapping | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT asana_workspace_gid, asana_workspace_name "
            "FROM asana_workspace_map WHERE workspace = ?",
            (workspace,),
        ).fetchone()
    if row is None:
        return None
    return WorkspaceMapping(
        workspace=workspace,
        asana_workspace_gid=row["asana_workspace_gid"],
        asana_workspace_name=row["asana_workspace_name"],
    )


def set_mapping(workspace: str, asana_gid: str, asana_name: str) -> None:
    now = int(time.time())
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO asana_workspace_map "
            "(workspace, asana_workspace_gid, asana_workspace_name, mapped_at) "
            "VALUES (?, ?, ?, ?) "
            "ON CONFLICT(workspace) DO UPDATE SET "
            "asana_workspace_gid = excluded.asana_workspace_gid, "
            "asana_workspace_name = excluded.asana_workspace_name, "
            "mapped_at = excluded.mapped_at",
            (workspace, asana_gid, asana_name, now),
        )


def clear_mapping(workspace: str) -> None:
    with db.connect() as conn:
        conn.execute(
            "DELETE FROM asana_workspace_map WHERE workspace = ?", (workspace,)
        )


def all_mappings() -> list[WorkspaceMapping]:
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT workspace, asana_workspace_gid, asana_workspace_name "
            "FROM asana_workspace_map"
        ).fetchall()
    return [
        WorkspaceMapping(
            workspace=r["workspace"],
            asana_workspace_gid=r["asana_workspace_gid"],
            asana_workspace_name=r["asana_workspace_name"],
        )
        for r in rows
    ]


# ---- local todo reads ----


def _row_to_todo(r) -> Todo:
    return Todo(
        gid=r["gid"],
        workspace=r["workspace"],
        name=r["name"],
        completed=bool(r["completed"]),
        due_on=r["due_on"],
        notes=r["notes"],
        modified_at=r["modified_at"],
        last_synced_at=r["last_synced_at"],
    )


def list_local(workspace: str, include_completed: bool = False) -> list[Todo]:
    sql = "SELECT * FROM todos WHERE workspace = ?"
    args: list = [workspace]
    if not include_completed:
        sql += " AND completed = 0"
    sql += " ORDER BY (due_on IS NULL), due_on ASC, name COLLATE NOCASE"
    with db.connect() as conn:
        rows = conn.execute(sql, args).fetchall()
    return [_row_to_todo(r) for r in rows]


def get_local(gid: str) -> Todo | None:
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM todos WHERE gid = ?", (gid,)).fetchone()
    return _row_to_todo(row) if row else None


# ---- upserts from Asana ----


def _upsert(workspace: str, t: asana_client.AsanaTask, *, now: int) -> None:
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO todos "
            "(gid, workspace, name, completed, due_on, notes, modified_at, last_synced_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(gid) DO UPDATE SET "
            "workspace = excluded.workspace, "
            "name = excluded.name, "
            "completed = excluded.completed, "
            "due_on = excluded.due_on, "
            "notes = excluded.notes, "
            "modified_at = excluded.modified_at, "
            "last_synced_at = excluded.last_synced_at",
            (
                t.gid,
                workspace,
                t.name,
                1 if t.completed else 0,
                t.due_on,
                t.notes,
                t.modified_at,
                now,
            ),
        )


# ---- write-through to Asana ----


async def create(workspace: str, name: str) -> Todo:
    mapping = get_mapping(workspace)
    if mapping is None:
        raise RuntimeError(f"workspace '{workspace}' has no Asana mapping")
    name = name.strip()
    if not name:
        raise ValueError("task name is required")
    task = await asana_client.create_task(mapping.asana_workspace_gid, name)
    now = int(time.time())
    _upsert(workspace, task, now=now)
    return _row_to_todo_from_asana(workspace, task, now)


async def toggle_complete(workspace: str, gid: str) -> Todo:
    local = get_local(gid)
    if local is None or local.workspace != workspace:
        raise RuntimeError(f"todo {gid} not found in workspace {workspace}")
    task = await asana_client.update_task(gid, completed=not local.completed)
    now = int(time.time())
    _upsert(workspace, task, now=now)
    return _row_to_todo_from_asana(workspace, task, now)


def _row_to_todo_from_asana(workspace: str, t: asana_client.AsanaTask, now: int) -> Todo:
    return Todo(
        gid=t.gid,
        workspace=workspace,
        name=t.name,
        completed=t.completed,
        due_on=t.due_on,
        notes=t.notes,
        modified_at=t.modified_at,
        last_synced_at=now,
    )


# ---- pull from Asana ----


async def sync_from_asana(workspace: str) -> int:
    """Pull incomplete tasks from Asana, upsert into local todos.

    Local todos still marked incomplete but not in the latest Asana response
    are flipped to completed=1 (Asana is the source of truth — the task
    either got completed there or was unassigned from us).

    Returns number of tasks upserted from Asana.
    """
    mapping = get_mapping(workspace)
    if mapping is None:
        return 0
    tasks = await asana_client.list_my_tasks(mapping.asana_workspace_gid)
    now = int(time.time())
    seen: set[str] = set()
    for t in tasks:
        _upsert(workspace, t, now=now)
        seen.add(t.gid)
    # Anything locally still open that Asana didn't return → consider done.
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT gid FROM todos WHERE workspace = ? AND completed = 0",
            (workspace,),
        ).fetchall()
        gone = [r["gid"] for r in rows if r["gid"] not in seen]
        if gone:
            placeholders = ",".join("?" * len(gone))
            conn.execute(
                f"UPDATE todos SET completed = 1, last_synced_at = ? "
                f"WHERE gid IN ({placeholders})",
                [now, *gone],
            )
    return len(tasks)
