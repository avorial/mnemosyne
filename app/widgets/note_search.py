"""Search Notes widget — find that thing you captured.

Search-as-you-type over the active workspace's vault checkout. Results
are recognition snippets, not reading: the note itself stays in Obsidian.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated

import mimetypes

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from app import auth
from app.services import note_search
from app.widget_api import Widget, registry

log = logging.getLogger("mnemosyne.widgets.note_search")

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()


def _current_workspace(request: Request) -> str:
    ws = request.cookies.get("workspace", "personal")
    return ws if ws in ("personal", "work") else "personal"


def _auth(session: auth.Session | None) -> HTMLResponse | None:
    if session is None:
        return HTMLResponse(status_code=401, content="not authenticated")
    return None


@router.get("/render", response_class=HTMLResponse)
def render(
    request: Request,
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if (r := _auth(session)) is not None:
        return r
    workspace = _current_workspace(request)
    return templates.TemplateResponse(
        "widgets/note_search.html",
        {"request": request, "workspace": workspace, "loaded": True, "q": "", "hits": None},
    )


@router.get("/search", response_class=HTMLResponse)
async def search(
    request: Request,
    q: Annotated[str, Query()] = "",
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if (r := _auth(session)) is not None:
        return r
    workspace = _current_workspace(request)
    q = q.strip()
    # Filesystem scan stays off the event loop.
    hits = await asyncio.to_thread(note_search.search, workspace, q) if q else None
    return templates.TemplateResponse(
        "widgets/_note_results.html",
        {"request": request, "workspace": workspace, "q": q, "hits": hits},
    )


@router.get("/note", response_class=HTMLResponse)
async def note(
    request: Request,
    path: Annotated[str, Query()],
    q: Annotated[str, Query()] = "",
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if (r := _auth(session)) is not None:
        return r
    workspace = _current_workspace(request)
    try:
        n = await asyncio.to_thread(note_search.read_note, workspace, path)
    except note_search.NoteNotFound:
        return HTMLResponse(status_code=404, content="note not found")
    return templates.TemplateResponse(
        "widgets/_note_view.html",
        {"request": request, "workspace": workspace, "q": q, "note": n},
    )


@router.get("/attachment")
async def attachment(
    request: Request,
    path: Annotated[str, Query()],
    session: auth.Session | None = Depends(auth.session_from_request),
) -> Response:
    if session is None:
        return Response(status_code=401)
    workspace = _current_workspace(request)
    try:
        f = note_search.resolve_in_vault(workspace, path)
    except note_search.NoteNotFound:
        return Response(status_code=404)
    media_type = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
    return FileResponse(f, media_type=media_type)


widget = Widget(
    id="note_search",
    title="Search Notes",
    description="Find that thing you captured. Snippets point into the vault.",
    default_size={"w": 4, "h": 5},
    router=router,
)
registry.register(widget)
