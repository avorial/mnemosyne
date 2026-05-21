"""Widget framework — base class, registry, layout persistence.

A widget is a self-contained module under `app/widgets/` that exports a
`widget` attribute holding a Widget instance. Modules are discovered on app
startup by scanning the `app.widgets` package.

v0.1 ships no widgets; the registry exists so v0.2+ can plug in.
"""

from __future__ import annotations

import importlib
import json
import pkgutil
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List

from app import db


@dataclass
class Widget:
    id: str
    title: str
    description: str = ""
    config_schema: Dict[str, Any] = field(default_factory=dict)
    default_size: Dict[str, int] = field(default_factory=lambda: {"w": 3, "h": 2})
    render: Callable[[Dict[str, Any]], str] | None = None
    actions: Dict[str, Callable[..., Any]] = field(default_factory=dict)


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
        return list(self._widgets.values())


registry = Registry()


def discover() -> None:
    """Import every module under app.widgets so each can self-register."""
    import app.widgets as pkg

    for _, name, _ in pkgutil.iter_modules(pkg.__path__):
        importlib.import_module(f"app.widgets.{name}")


def get_layout(workspace: str) -> List[Dict[str, Any]]:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT layout_json FROM layouts WHERE workspace = ?",
            (workspace,),
        ).fetchone()
    if row is None:
        return []
    try:
        return json.loads(row["layout_json"])
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
