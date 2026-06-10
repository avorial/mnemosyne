"""Todo widget — two-way sync with Asana.

Source of truth is Asana. SQLite mirrors. Writes go to Asana first, then to
the local mirror.

First-time setup per Mnemosyne workspace: a picker chooses which Asana
workspace this Mnemosyne workspace maps to.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import auth
from app.config import config
from app.services import asana_client, secret_files, todos
from app.widget_api import Widget, registry

log = logging.getLogger("mnemosyne.widgets.todo_asana")

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()


def _current_workspace(request: Request) -> str:
    ws = request.cookies.get("workspace", "personal")
    return ws if ws in ("personal", "work") else "personal"


async def _render(
    request: Request,
    workspace: str,
    flash: dict | None = None,
) -> HTMLResponse:
    pat_configured = bool(config.asana_pat)
    mapping = todos.get_mapping(workspace) if pat_configured else None
    available_workspaces: list[asana_client.AsanaWorkspace] = []
    todo_list: list[todos.Todo] = []
    sync_error: str | None = None
    if pat_configured and mapping is None:
        try:
            available_workspaces = await asana_client.list_workspaces()
        except asana_client.AsanaError as e:
            sync_error = str(e)
    if pat_configured and mapping is not None:
        todo_list = todos.list_local(workspace)
    return templates.TemplateResponse(
        "widgets/todo_asana.html",
        {
            "request": request,
            "workspace": workspace,
            "flash": flash,
            "item": None,
            "pat_configured": pat_configured,
            "pat_file": str(config.asana_pat_file),
            "mapping": mapping,
            "available_workspaces": available_workspaces,
            "todos": todo_list,
            "sync_error": sync_error,
        },
    )


def _auth(session: auth.Session | None) -> HTMLResponse | None:
    if session is None:
        return HTMLResponse(status_code=401, content="not authenticated")
    return None


@router.get("/render", response_class=HTMLResponse)
async def render(
    request: Request,
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if (r := _auth(session)) is not None:
        return r
    workspace = _current_workspace(request)
    return await _render(request, workspace)


@router.post("/set_token", response_class=HTMLResponse)
async def set_token(
    request: Request,
    token: Annotated[str, Form()],
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if (r := _auth(session)) is not None:
        return r
    workspace = _current_workspace(request)
    secret_files.write_secret(config.asana_pat_file, token)
    return await _render(request, workspace)


@router.post("/set_workspace", response_class=HTMLResponse)
async def set_workspace(
    request: Request,
    asana_workspace_gid: Annotated[str, Form()],
    asana_workspace_name: Annotated[str, Form()],
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if (r := _auth(session)) is not None:
        return r
    workspace = _current_workspace(request)
    todos.set_mapping(workspace, asana_workspace_gid, asana_workspace_name)
    flash: dict[str, str] = {"kind": "ok", "message": f"Mapped to {asana_workspace_name}"}
    try:
        count = await todos.sync_from_asana(workspace)
        flash["message"] = f"Mapped to {asana_workspace_name} — pulled {count} task(s)"
    except asana_client.AsanaError as e:
        flash = {"kind": "err", "message": f"Mapped, but initial pull failed: {e}"}
    return await _render(request, workspace, flash)


@router.post("/clear_workspace", response_class=HTMLResponse)
async def clear_workspace(
    request: Request,
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if (r := _auth(session)) is not None:
        return r
    workspace = _current_workspace(request)
    todos.clear_mapping(workspace)
    return await _render(request, workspace, {"kind": "ok", "message": "Workspace unmapped"})


@router.post("/create", response_class=HTMLResponse)
async def create(
    request: Request,
    name: Annotated[str, Form()],
    save_to: Annotated[str, Form(alias="workspace")] = "",
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if (r := _auth(session)) is not None:
        return r
    active = _current_workspace(request)
    target = save_to if save_to in ("personal", "work") else active
    try:
        t = await todos.create(target, name)
        where = f"Added to {target}" if target != active else "Added"
        flash = {"kind": "ok", "message": f"{where}: {t.name}"}
    except (asana_client.AsanaError, ValueError, RuntimeError) as e:
        log.exception("todo create failed")
        flash = {"kind": "err", "message": f"Add failed: {e}"}
    return await _render(request, active, flash)


@router.post("/toggle", response_class=HTMLResponse)
async def toggle(
    request: Request,
    gid: Annotated[str, Form()],
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if (r := _auth(session)) is not None:
        return r
    workspace = _current_workspace(request)
    try:
        t = await todos.toggle_complete(workspace, gid)
        verb = "Completed" if t.completed else "Reopened"
        flash = {"kind": "ok", "message": f"{verb}: {t.name}"}
    except (asana_client.AsanaError, RuntimeError) as e:
        log.exception("todo toggle failed")
        flash = {"kind": "err", "message": f"Toggle failed: {e}"}
    return await _render(request, workspace, flash)


@router.post("/refresh", response_class=HTMLResponse)
async def refresh(
    request: Request,
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if (r := _auth(session)) is not None:
        return r
    workspace = _current_workspace(request)
    try:
        count = await todos.sync_from_asana(workspace)
        flash = {"kind": "ok", "message": f"Pulled {count} task(s) from Asana"}
    except (asana_client.AsanaError, RuntimeError) as e:
        flash = {"kind": "err", "message": f"Sync failed: {e}"}
    return await _render(request, workspace, flash)


widget = Widget(
    id="todo_asana",
    title="Todos (Asana)",
    description="Two-way sync with one Asana workspace per Mnemosyne workspace.",
    default_size={"w": 5, "h": 6},
    router=router,
)
registry.register(widget)
