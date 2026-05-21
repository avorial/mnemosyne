"""Asana API client — async httpx wrapper.

Auth: Personal Access Token (PAT) read from ASANA_PAT_FILE. Bearer header.

This is the surface area we currently need:
- list_workspaces
- list_my_tasks(workspace_gid)
- create_task(workspace_gid, name)
- update_task(gid, ...)            # name, completed, notes, due_on, ...
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import config

log = logging.getLogger("mnemosyne.asana")

BASE_URL = "https://app.asana.com/api/1.0"
TIMEOUT_SECONDS = 15.0
TASK_OPT_FIELDS = "name,completed,due_on,notes,modified_at,assignee.gid"


class AsanaError(RuntimeError):
    pass


class AsanaNotConfigured(AsanaError):
    pass


@dataclass(frozen=True)
class AsanaWorkspace:
    gid: str
    name: str


@dataclass
class AsanaTask:
    gid: str
    name: str
    completed: bool
    due_on: str | None
    notes: str
    modified_at: str   # ISO 8601


def _headers() -> dict[str, str]:
    token = config.asana_pat
    if not token:
        raise AsanaNotConfigured(
            f"Asana PAT not configured (looked at {config.asana_pat_file})"
        )
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }


async def _request(method: str, path: str, **kwargs: Any) -> dict:
    url = f"{BASE_URL}{path}"
    headers = _headers()
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, headers=headers) as client:
        resp = await client.request(method, url, **kwargs)
    if resp.status_code >= 400:
        raise AsanaError(
            f"Asana {method} {path} → {resp.status_code}: {resp.text[:300]}"
        )
    return resp.json()


async def list_workspaces() -> list[AsanaWorkspace]:
    data = await _request("GET", "/workspaces", params={"opt_fields": "name"})
    return [AsanaWorkspace(gid=w["gid"], name=w["name"]) for w in data.get("data", [])]


def _task_from_dict(d: dict) -> AsanaTask:
    return AsanaTask(
        gid=d["gid"],
        name=d.get("name", ""),
        completed=bool(d.get("completed", False)),
        due_on=d.get("due_on"),
        notes=d.get("notes", "") or "",
        modified_at=d.get("modified_at", "") or "",
    )


async def list_my_tasks(workspace_gid: str, include_completed: bool = False) -> list[AsanaTask]:
    """Tasks assigned to me in the given workspace."""
    params: dict[str, Any] = {
        "assignee": "me",
        "workspace": workspace_gid,
        "opt_fields": TASK_OPT_FIELDS,
        "limit": 100,
    }
    if not include_completed:
        # `completed_since=now` filters to only incomplete tasks.
        params["completed_since"] = "now"
    out: list[AsanaTask] = []
    next_offset: str | None = None
    while True:
        if next_offset:
            params["offset"] = next_offset
        data = await _request("GET", "/tasks", params=params)
        out.extend(_task_from_dict(t) for t in data.get("data", []))
        nxt = (data.get("next_page") or {}) or {}
        next_offset = nxt.get("offset")
        if not next_offset:
            break
    return out


async def create_task(workspace_gid: str, name: str, notes: str = "") -> AsanaTask:
    payload = {
        "data": {
            "name": name,
            "notes": notes,
            "assignee": "me",
            "workspace": workspace_gid,
        }
    }
    data = await _request(
        "POST", "/tasks",
        params={"opt_fields": TASK_OPT_FIELDS},
        json=payload,
    )
    return _task_from_dict(data["data"])


async def update_task(
    gid: str,
    *,
    name: str | None = None,
    completed: bool | None = None,
    notes: str | None = None,
    due_on: str | None = None,
) -> AsanaTask:
    data_fields: dict[str, Any] = {}
    if name is not None:
        data_fields["name"] = name
    if completed is not None:
        data_fields["completed"] = completed
    if notes is not None:
        data_fields["notes"] = notes
    if due_on is not None:
        data_fields["due_on"] = due_on or None
    if not data_fields:
        raise ValueError("update_task called with no changes")
    data = await _request(
        "PUT", f"/tasks/{gid}",
        params={"opt_fields": TASK_OPT_FIELDS},
        json={"data": data_fields},
    )
    return _task_from_dict(data["data"])


async def get_task(gid: str) -> AsanaTask:
    data = await _request(
        "GET", f"/tasks/{gid}", params={"opt_fields": TASK_OPT_FIELDS}
    )
    return _task_from_dict(data["data"])
