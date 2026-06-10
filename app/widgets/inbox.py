"""Inbox widget — drop zone for text, pasted images, and dragged files.

Each save creates one note under Inbox/ and (optionally) one or more files
under _attachments/. Everything commits to the active workspace's vault.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import auth
from app.services import vault
from app.widget_api import Widget, registry

log = logging.getLogger("mnemosyne.widgets.inbox")

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()


def _current_workspace(request: Request) -> str:
    ws = request.cookies.get("workspace", "personal")
    return ws if ws in ("personal", "work") else "personal"


def _render(request: Request, workspace: str, flash: dict | None) -> HTMLResponse:
    return templates.TemplateResponse(
        "widgets/inbox.html",
        {"request": request, "workspace": workspace, "flash": flash, "item": None},
    )


@router.post("/save", response_class=HTMLResponse)
async def save(
    request: Request,
    body: Annotated[str, Form()] = "",
    files: Annotated[list[UploadFile], File()] = [],
    save_to: Annotated[str, Form(alias="workspace")] = "",
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if session is None:
        return HTMLResponse(status_code=401, content="not authenticated")
    active = _current_workspace(request)
    target = save_to if save_to in ("personal", "work") else active
    body = (body or "").strip()
    valid_files = [f for f in files if f and f.filename]
    if not body and not valid_files:
        return _render(
            request,
            active,
            {"kind": "err", "message": "Nothing to save. Drop a file, paste, or type."},
        )

    saved: list[Path] = []
    try:
        for f in valid_files:
            content = await f.read()
            if not content:
                continue
            saved.append(
                await asyncio.to_thread(
                    vault.save_attachment, target, f.filename, content
                )
            )
        # write_inbox does git add/commit/push — keep it off the event loop.
        note_abs = await asyncio.to_thread(
            vault.write_inbox, target, body, saved
        )
        rel = note_abs.relative_to(vault.WORKSPACES[target].path)
        where = f"{target}: {rel.as_posix()}" if target != active else rel.as_posix()
        msg = f"Saved {where}"
        if saved:
            msg += f" + {len(saved)} attachment" + ("s" if len(saved) != 1 else "")
        flash = {"kind": "ok", "message": msg}
    except vault.VaultError as e:
        log.exception("inbox save failed")
        flash = {"kind": "err", "message": f"Save failed: {e}"}
    return _render(request, active, flash)


widget = Widget(
    id="inbox",
    title="Inbox",
    description="Drop files, paste images, or jot a thought — lands in Inbox/ with attachments under _attachments/.",
    default_size={"w": 5, "h": 5},
    router=router,
)
registry.register(widget)
