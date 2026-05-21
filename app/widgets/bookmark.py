"""Bookmark widget — capture a URL with fetched title/description."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import auth
from app.services import bookmarks, link_fetch, vault
from app.widget_api import Widget, registry

log = logging.getLogger("mnemosyne.widgets.bookmark")

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()


def _current_workspace(request: Request) -> str:
    ws = request.cookies.get("workspace", "personal")
    return ws if ws in ("personal", "work") else "personal"


def _render(
    request: Request,
    workspace: str,
    flash: dict | None,
    q: str = "",
) -> HTMLResponse:
    items = bookmarks.search(workspace, q=q, limit=30)
    return templates.TemplateResponse(
        "widgets/bookmark.html",
        {
            "request": request,
            "workspace": workspace,
            "flash": flash,
            "item": None,
            "bookmarks": items,
            "q": q,
        },
    )


@router.get("/render", response_class=HTMLResponse)
def render(
    request: Request,
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if session is None:
        return HTMLResponse(status_code=401, content="not authenticated")
    workspace = _current_workspace(request)
    return _render(request, workspace, None)


@router.post("/save", response_class=HTMLResponse)
async def save(
    request: Request,
    url: Annotated[str, Form()],
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if session is None:
        return HTMLResponse(status_code=401, content="not authenticated")
    workspace = _current_workspace(request)
    url = (url or "").strip()
    if not url:
        return _render(request, workspace, {"kind": "err", "message": "URL required"})
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    try:
        meta = await link_fetch.fetch_meta(url)
    except ValueError as e:
        return _render(request, workspace, {"kind": "err", "message": str(e)})

    title = meta.title or meta.url
    try:
        # vault.write_bookmark runs blocking git subprocesses; push it off
        # the event loop so other requests (incl. /healthz) stay responsive
        # while git is talking to GitHub.
        abs_path = await asyncio.to_thread(
            vault.write_bookmark, workspace, meta.url, title, meta.description
        )
    except vault.VaultError as e:
        log.exception("bookmark write failed")
        return _render(request, workspace, {"kind": "err", "message": f"Save failed: {e}"})

    relpath = abs_path.relative_to(vault.WORKSPACES[workspace].path).as_posix()
    bookmarks.insert(workspace, meta.url, title, meta.description, relpath)
    return _render(
        request,
        workspace,
        {"kind": "ok", "message": f"Saved {relpath}"},
    )


@router.get("/list", response_class=HTMLResponse)
def list_(
    request: Request,
    q: Annotated[str, Query()] = "",
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if session is None:
        return HTMLResponse(status_code=401, content="not authenticated")
    workspace = _current_workspace(request)
    items = bookmarks.search(workspace, q=q, limit=30)
    return templates.TemplateResponse(
        "widgets/_bookmark_list.html",
        {"request": request, "bookmarks": items, "q": q, "workspace": workspace},
    )


widget = Widget(
    id="bookmark",
    title="Bookmark",
    description="Paste a URL; we fetch the title/description and save Links/<slug>.md.",
    default_size={"w": 5, "h": 5},
    router=router,
)
registry.register(widget)
