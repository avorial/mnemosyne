"""Widget framework — base class, registry, layout persistence.

A widget is a self-contained module under `app/widgets/`. Each module imports
this file, builds a `Widget` instance, and registers it. On startup,
`discover()` imports every submodule so they self-register.

Widgets can optionally expose a FastAPI `APIRouter`; routers are mounted by
`app.main` under `/widgets/{widget_id}/...`.

Each widget should also provide a Jinja partial at
`app/templates/widgets/{widget_id}.html` — the dashboard includes that
partial for every instance in the active workspace's layout.
"""

from __future__ import annotations

import importlib
import json
import pkgutil
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List

from fastapi import APIRouter

from app import db


@dataclass
class Widget:
    id: str
    title: str
    description: str = ""
    default_size: Dict[str, int] = field(default_factory=lambda: {"w": 4, "h": 3})
    router: APIRouter | None = None


class Registry:
    def __init__(self) -> None:
        self._widgets: Dict[str, Widget] = {}

    def register(self, widget: Widget) -> None:
        if widget.id in self._widgets:
            raise ValueError(f"widget '{widget.id}' already registered")
        self._widgets[widget.id] = widget

    def get(self, widget_id: str) -> Widget | None:
        return self._widgets.get(widget_id)

    def all(self) -> List[Widget]:
        return sorted(self._widgets.values(), key=lambda w: w.title.lower())


registry = Registry()


def discover() -> List[Widget]:
    """Import every module under app.widgets so each can self-register."""
    import app.widgets as pkg

    for _, name, _ in pkgutil.iter_modules(pkg.__path__):
        importlib.import_module(f"app.widgets.{name}")
    return registry.all()


# ---------- layout persistence ----------
# A layout is a list of instance dicts:
#   { "id": "<uuid>", "widget_id": "quick_note", "x": 0, "y": 0, "w": 4, "h": 3 }


def get_layout(workspace: str) -> List[Dict[str, Any]]:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT layout_json FROM layouts WHERE workspace = ?",
            (workspace,),
        ).fetchone()
    if row is None:
        return []
    try:
        items = json.loads(row["layout_json"])
        if not isinstance(items, list):
            return []
        return items
    except json.JSONDecodeError:
        return []


def save_layout(workspace: str, layout: List[Dict[str, Any]]) -> None:
    now = int(time.time())
    payload = json.dumps(layout)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO layouts (workspace, layout_json, updated_at) VALUES (?, ?, ?) "
            "ON CONFLICT(workspace) DO UPDATE SET layout_json = excluded.layout_json, "
            "updated_at = excluded.updated_at",
            (workspace, payload, now),
        )


def add_to_layout(workspace: str, widget_id: str) -> Dict[str, Any]:
    widget = registry.get(widget_id)
    if widget is None:
        raise ValueError(f"unknown widget '{widget_id}'")
    items = get_layout(workspace)
    instance = {
        "id": str(uuid.uuid4()),
        "widget_id": widget_id,
        "x": 0,
        "y": _next_y(items),
        "w": widget.default_size.get("w", 4),
        "h": widget.default_size.get("h", 3),
    }
    items.append(instance)
    save_layout(workspace, items)
    return instance


def remove_from_layout(workspace: str, instance_id: str) -> bool:
    items = get_layout(workspace)
    filtered = [it for it in items if it.get("id") != instance_id]
    if len(filtered) == len(items):
        return False
    save_layout(workspace, filtered)
    return True


def _next_y(items: List[Dict[str, Any]]) -> int:
    """Place a new widget below all existing ones to avoid overlap."""
    if not items:
        return 0
    return max((int(it.get("y", 0)) + int(it.get("h", 1))) for it in items)
