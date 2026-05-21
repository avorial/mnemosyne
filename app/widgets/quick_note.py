"""Quick Note widget — append a thought to today's daily note."""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import auth
from app.services import vault
from app.widget_api import Widget, registry

log = logging.getLogger("mnemosyne.widgets.quick_note")

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()


def _current_workspace(request: Request) -> str:
    ws = request.cookies.get("workspace", "personal")
    return ws if ws in ("personal", "work") else "personal"


@router.post("/save", response_class=HTMLResponse)
def save(
    request: Request,
    body: str = Form(...),
    session: auth.Session = Depends(auth.session_from_request),
):
    if session is None:
        return HTMLResponse(status_code=401, content="not authenticated")
    workspace = _current_workspace(request)
    flash: dict[str, str]
    try:
        written = vault.append_to_daily(workspace, body)
        rel = written.relative_to(vault.WORKSPACES[workspace].path)
        flash = {"kind": "ok", "message": f"Saved to {rel.as_posix()}"}
    except vault.VaultError as e:
        log.exception("vault write failed")
        flash = {"kind": "err", "message": f"Save failed: {e}"}
    return templates.TemplateResponse(
        "widgets/quick_note.html",
        {"request": request, "workspace": workspace, "flash": flash, "item": None},
    )


widget = Widget(
    id="quick_note",
    title="Quick Note",
    description="Append a thought to today's daily note in the active workspace.",
    default_size={"w": 4, "h": 4},
    router=router,
)
registry.register(widget)
