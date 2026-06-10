"""GitHub activity widget — recent commits, PRs, and issues at a glance.

One feed for the authenticated PAT user, shown in both workspaces. Fetched
live on each render via the dashboard's lazy-load pattern.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import auth
from app.config import config
from app.services import github_client, secret_files
from app.widget_api import Widget, registry

log = logging.getLogger("mnemosyne.widgets.github_activity")

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()


def _current_workspace(request: Request) -> str:
    ws = request.cookies.get("workspace", "personal")
    return ws if ws in ("personal", "work") else "personal"


def _ago(at: datetime) -> str:
    delta = datetime.now(timezone.utc) - at
    seconds = int(delta.total_seconds())
    if seconds < 90:
        return "now"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h"
    days = hours // 24
    if days < 14:
        return f"{days}d"
    return f"{days // 7}w"


async def _render(request: Request, workspace: str) -> HTMLResponse:
    pat_configured = bool(config.github_pat)
    rows: list[dict] = []
    error: str | None = None
    if pat_configured:
        try:
            for a in await github_client.recent_activity():
                rows.append(
                    {
                        "summary": a.summary,
                        "repo": a.repo.split("/")[-1],
                        "url": a.url,
                        "ago": _ago(a.at),
                    }
                )
        except github_client.GitHubError as e:
            log.warning("github fetch failed: %s", e)
            error = str(e)
    return templates.TemplateResponse(
        "widgets/github_activity.html",
        {
            "request": request,
            "workspace": workspace,
            "loaded": True,
            "pat_configured": pat_configured,
            "pat_file": str(config.github_pat_file),
            "rows": rows,
            "error": error,
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
    return await _render(request, _current_workspace(request))


@router.post("/set_token", response_class=HTMLResponse)
async def set_token(
    request: Request,
    token: Annotated[str, Form()],
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if (r := _auth(session)) is not None:
        return r
    workspace = _current_workspace(request)
    secret_files.write_secret(config.github_pat_file, token)
    return await _render(request, workspace)


widget = Widget(
    id="github_activity",
    title="GitHub",
    description="Recent commits, pull requests, and issues.",
    default_size={"w": 4, "h": 5},
    router=router,
)
registry.register(widget)
