"""Calendar widget — a glance at today and tomorrow.

Per PRODUCT.md, the personal workspace glances Google Calendar and the work
workspace glances the Microsoft 365 calendar. Events are fetched live on each
render (the dashboard lazy-loads widgets, so this never blocks page load).

Two ways to connect, checked in this order:

1. **Pasted secret address (ICS)** — the zero-setup path. Log into the
   provider, copy the calendar's secret/published ICS link, paste it into
   the widget. See services/ics_calendar.py.
2. **OAuth** — only offered when client credentials are configured in the
   environment. See services/google_calendar.py / ms_calendar.py.
"""

from __future__ import annotations

import logging
from datetime import datetime, time as dtime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from itsdangerous import BadSignature, URLSafeTimedSerializer

from app import auth
from app.config import config
from app.services import google_calendar, ics_calendar, ms_calendar
from app.services.calendar_types import CalendarError, CalendarNotConnected, CalEvent, local_tz
from app.widget_api import Widget, registry

log = logging.getLogger("mnemosyne.widgets.calendar")

BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

router = APIRouter()

STATE_MAX_AGE_SECONDS = 600

PROVIDERS = {
    "google": {
        "name": "Google Calendar",
        "module": google_calendar,
        "configured": lambda: config.google_configured,
        "ics_hint": (
            "In Google Calendar: Settings, pick your calendar, Integrate calendar, "
            "copy the Secret address in iCal format."
        ),
    },
    "ms": {
        "name": "Microsoft 365",
        "module": ms_calendar,
        "configured": lambda: config.ms_configured,
        "ics_hint": (
            "In Outlook on the web: Settings, Calendar, Shared calendars, "
            "Publish a calendar, copy the ICS link."
        ),
    },
}


def _provider_for(workspace: str) -> str:
    return "google" if workspace == "personal" else "ms"


def _current_workspace(request: Request) -> str:
    ws = request.cookies.get("workspace", "personal")
    return ws if ws in ("personal", "work") else "personal"


def _state_serializer() -> URLSafeTimedSerializer:
    return URLSafeTimedSerializer(config.secret_key, salt="calendar-oauth")


def _window() -> tuple[datetime, datetime]:
    tz = local_tz()
    start = datetime.combine(datetime.now(tz).date(), dtime.min, tzinfo=tz)
    return start, start + timedelta(days=2)


def _day_buckets(events: list[CalEvent]) -> list[dict]:
    tz = local_tz()
    today = datetime.now(tz).date()
    tomorrow = today + timedelta(days=1)
    # %-d / %#d are platform-specific; build "Tue Jun 10" portably.
    buckets = [
        {"label": "Today", "date_label": f"{today.strftime('%a %b')} {today.day}", "events": []},
        {"label": "Tomorrow", "date_label": f"{tomorrow.strftime('%a %b')} {tomorrow.day}", "events": []},
    ]
    for ev in events:
        day = max(ev.start.date(), today)  # clamp multi-day all-day events
        if day == today:
            buckets[0]["events"].append(ev)
        elif day == tomorrow:
            buckets[1]["events"].append(ev)
    for b in buckets:
        b["events"].sort(key=lambda e: (not e.all_day, e.start))
    return buckets


async def _render(request: Request, workspace: str, flash: dict | None = None) -> HTMLResponse:
    provider_id = _provider_for(workspace)
    provider = PROVIDERS[provider_id]
    mod = provider["module"]
    oauth_available = provider["configured"]()

    mode = "setup"
    account: str | None = None
    days: list[dict] = []
    error: str | None = None

    if ics_calendar.get_url(workspace):
        mode = "ics"
        account = await ics_calendar.connected_name(workspace)
        try:
            start, end = _window()
            days = _day_buckets(await ics_calendar.list_events(workspace, start, end))
        except CalendarError as e:
            log.warning("ics fetch failed: %s", e)
            error = str(e)
    elif oauth_available and mod.connected_account() is not None:
        mode = "oauth"
        account = mod.connected_account()
        try:
            start, end = _window()
            days = _day_buckets(await mod.list_events(start, end))
        except CalendarNotConnected:
            mode, account = "setup", None
        except CalendarError as e:
            log.warning("calendar fetch failed: %s", e)
            error = str(e)

    return templates.TemplateResponse(
        "widgets/calendar.html",
        {
            "request": request,
            "workspace": workspace,
            "loaded": True,
            "flash": flash,
            "mode": mode,
            "provider": provider_id,
            "provider_name": provider["name"],
            "ics_hint": provider["ics_hint"],
            "oauth_available": oauth_available,
            "account": account,
            "days": days,
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


@router.post("/set_ics", response_class=HTMLResponse)
async def set_ics(
    request: Request,
    url: Annotated[str, Form()],
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if (r := _auth(session)) is not None:
        return r
    workspace = _current_workspace(request)
    flash: dict[str, str] | None = None
    try:
        ics_calendar.set_url(workspace, url)
        # Validate immediately so a bad paste fails here, not on every glance.
        start, end = _window()
        await ics_calendar.list_events(workspace, start, end)
        flash = {"kind": "ok", "message": "Calendar connected"}
    except CalendarError as e:
        ics_calendar.clear_url(workspace)
        flash = {"kind": "err", "message": str(e)}
    return await _render(request, workspace, flash)


@router.post("/clear_ics", response_class=HTMLResponse)
async def clear_ics(
    request: Request,
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if (r := _auth(session)) is not None:
        return r
    workspace = _current_workspace(request)
    ics_calendar.clear_url(workspace)
    return await _render(request, workspace, {"kind": "ok", "message": "Calendar disconnected"})


@router.get("/{provider_id}/connect")
async def connect(
    provider_id: str,
    request: Request,
    session: auth.Session | None = Depends(auth.session_from_request),
) -> Response:
    if session is None:
        return RedirectResponse("/login", status_code=302)
    provider = PROVIDERS.get(provider_id)
    if provider is None or not provider["configured"]():
        return RedirectResponse("/", status_code=302)
    state = _state_serializer().dumps({"provider": provider_id})
    return RedirectResponse(provider["module"].auth_url(state), status_code=302)


@router.get("/{provider_id}/callback")
async def callback(
    provider_id: str,
    request: Request,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    session: auth.Session | None = Depends(auth.session_from_request),
) -> Response:
    if session is None:
        return RedirectResponse("/login", status_code=302)
    provider = PROVIDERS.get(provider_id)
    if provider is None:
        return RedirectResponse("/", status_code=302)
    if error or not code or not state:
        log.warning("oauth callback error for %s: %s", provider_id, error)
        return RedirectResponse("/", status_code=302)
    try:
        payload = _state_serializer().loads(state, max_age=STATE_MAX_AGE_SECONDS)
        if payload.get("provider") != provider_id:
            raise BadSignature("provider mismatch")
    except BadSignature:
        log.warning("oauth state rejected for %s", provider_id)
        return RedirectResponse("/", status_code=302)
    try:
        await provider["module"].exchange_code(code)
    except CalendarError:
        log.exception("oauth code exchange failed for %s", provider_id)
    return RedirectResponse("/", status_code=302)


@router.post("/disconnect", response_class=HTMLResponse)
async def disconnect(
    request: Request,
    session: auth.Session | None = Depends(auth.session_from_request),
) -> HTMLResponse:
    if (r := _auth(session)) is not None:
        return r
    workspace = _current_workspace(request)
    PROVIDERS[_provider_for(workspace)]["module"].disconnect()
    return await _render(request, workspace)


widget = Widget(
    id="calendar",
    title="Calendar",
    description="Today and tomorrow at a glance. Google for personal, Microsoft 365 for work.",
    default_size={"w": 4, "h": 5},
    router=router,
)
registry.register(widget)
