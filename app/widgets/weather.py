"""Weather widget — Open-Meteo glance, no API key, based on where you are.

Default mode follows the device: the browser supplies coordinates (see
bindWeatherLocate in dashboard.js), the name comes from a keyless reverse
geocoder. Pinning a place by name is the explicit override, and the
fallback when location access is denied.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Query, Request
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


def _auth(session: auth.Session | None) -> HTMLResponse | None:
    if session is None:
        return HTMLResponse(status_code=401, content="not authenticated")
    return None


def _template(request: Request, workspace: str, ctx: dict) -> HTMLResponse:
    base = {"request": request, "workspace": workspace, "loaded": True,
            "mode": "setup", "flash": None, "wx": None, "error": None,
            "lat": None, "lon": None, "denied": False}
    return templates.TemplateResponse("widgets/weather.html", {**base, **ctx})


async def _forecast_ctx(loc: weather.Location) -> dict:
    try:
        return {"wx": await weather.forecast(loc)}
    except weather.WeatherError as e:
        log.warning("forecast failed: %s", e)
        return {"error": str(e)}


@router.get("/render", response_class=HTMLResponse)
async def render(
    request: Request,
    lat: Annotated[float | None, Query()] = None,
    lon: Annotated[float | None, Query()] = None,
    setup: Annotated[bool, Query()] = False,
    denied: Annotated[bool, Query()] = False,
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if (r := _auth(session)) is not None:
        return r
    workspace = _current_workspace(request)

    if setup or denied:
        return _template(request, workspace, {"mode": "setup", "denied": denied})

    if lat is not None and lon is not None:
        name = await weather.reverse_name(lat, lon) or "Current location"
        loc = weather.Location(name=name, latitude=lat, longitude=lon)
        ctx = await _forecast_ctx(loc)
        return _template(request, workspace, {"mode": "local", "lat": lat, "lon": lon, **ctx})

    pinned = weather.get_location()
    if pinned is not None:
        ctx = await _forecast_ctx(pinned)
        return _template(request, workspace, {"mode": "pinned", **ctx})

    # No pin: hand the browser a locate shell; JS supplies coordinates.
    return _template(request, workspace, {"mode": "locate"})


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
    except weather.WeatherError as e:
        return _template(request, workspace, {"mode": "setup", "flash": {"kind": "err", "message": str(e)}})
    ctx = await _forecast_ctx(loc)
    return _template(request, workspace, {
        "mode": "pinned",
        "flash": {"kind": "ok", "message": f"Pinned to {loc.name}"},
        **ctx,
    })


@router.post("/clear_location", response_class=HTMLResponse)
async def clear_location(
    request: Request,
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if (r := _auth(session)) is not None:
        return r
    weather.clear_location()
    # Back to follow-me mode: the locate shell re-asks the browser.
    return _template(request, _current_workspace(request), {"mode": "locate"})


widget = Widget(
    id="weather",
    title="Weather",
    description="The sky where you are. Open-Meteo, no key needed.",
    default_size={"w": 3, "h": 4},
    router=router,
)
registry.register(widget)
