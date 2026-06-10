"""Weather widget — Open-Meteo glance, no API key.

Setup is typing a place name once. The location is global (not per
workspace); the sky over the desk is the same either way.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app import auth
from app.services import weather
from app.widget_api import Widget, registry

log = logging.getLogger("mnemosyne.widgets.weather")

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()


def _current_workspace(request: Request) -> str:
    ws = request.cookies.get("workspace", "personal")
    return ws if ws in ("personal", "work") else "personal"


async def _render(request: Request, workspace: str, flash: dict | None = None) -> HTMLResponse:
    location = weather.get_location()
    data: dict | None = None
    error: str | None = None
    if location is not None:
        try:
            data = await weather.forecast()
        except weather.WeatherError as e:
            log.warning("forecast failed: %s", e)
            error = str(e)
    return templates.TemplateResponse(
        "widgets/weather.html",
        {
            "request": request,
            "workspace": workspace,
            "loaded": True,
            "flash": flash,
            "location": location,
            "wx": data,
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


@router.post("/set_location", response_class=HTMLResponse)
async def set_location(
    request: Request,
    q: Annotated[str, Form()],
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if (r := _auth(session)) is not None:
        return r
    workspace = _current_workspace(request)
    try:
        loc = await weather.set_location_by_name(q)
        flash = {"kind": "ok", "message": f"Watching the sky over {loc.name}"}
    except weather.WeatherError as e:
        flash = {"kind": "err", "message": str(e)}
    return await _render(request, workspace, flash)


@router.post("/clear_location", response_class=HTMLResponse)
async def clear_location(
    request: Request,
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if (r := _auth(session)) is not None:
        return r
    weather.clear_location()
    return await _render(request, _current_workspace(request))


widget = Widget(
    id="weather",
    title="Weather",
    description="Now, today, tomorrow. Open-Meteo, no key needed.",
    default_size={"w": 3, "h": 4},
    router=router,
)
registry.register(widget)
