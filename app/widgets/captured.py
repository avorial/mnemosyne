"""Captured widget — proof that today's captures landed.

Reads the capture log for the active workspace. A trust glance, not an
archive; the content itself lives in Obsidian, Asana, and the vault.
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import auth
from app.services import captures
from app.widget_api import Widget, registry

log = logging.getLogger("mnemosyne.widgets.captured")

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()

KIND_LABEL = {
    "note": "note",
    "inbox": "inbox",
    "bookmark": "link",
    "todo": "todo",
    "share": "share",
}


def _current_workspace(request: Request) -> str:
    ws = request.cookies.get("workspace", "personal")
    return ws if ws in ("personal", "work") else "personal"


def _clock(dt) -> str:
    h = dt.hour % 12 or 12
    suffix = "a" if dt.hour < 12 else "p"
    return f"{h}:{dt.minute:02d}{suffix}"


@router.get("/render", response_class=HTMLResponse)
def render(
    request: Request,
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if session is None:
        return HTMLResponse(status_code=401, content="not authenticated")
    workspace = _current_workspace(request)
    total, rows = captures.today(workspace)
    return templates.TemplateResponse(
        "widgets/captured.html",
        {
            "request": request,
            "workspace": workspace,
            "loaded": True,
            "total": total,
            "rows": [
                {"time": _clock(c.at), "kind": KIND_LABEL.get(c.kind, c.kind), "summary": c.summary}
                for c in rows
            ],
        },
    )


widget = Widget(
    id="captured",
    title="Captured",
    description="What landed today, so you never wonder whether it saved.",
    default_size={"w": 4, "h": 4},
    router=router,
)
registry.register(widget)
