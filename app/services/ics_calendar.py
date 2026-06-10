"""ICS calendar source — paste a secret calendar address, no API setup.

Both calendar providers publish per-calendar secret ICS URLs behind a
normal login, which makes this the zero-setup path:

- Google Calendar: Settings > [your calendar] > Integrate calendar >
  "Secret address in iCal format".
- Outlook / Microsoft 365: Settings > Calendar > Shared calendars >
  Publish a calendar > copy the ICS link.

The URL itself is the credential (anyone holding it can read the
calendar), so it lives as a file under the secrets dir like every other
secret, one per Mnemosyne workspace. Provider feeds refresh on their own
schedule (minutes to a few hours); fine for a glance.
"""

from __future__ import annotations

import logging
import time
from datetime import date, datetime
from pathlib import Path

import httpx
import icalendar
import recurring_ical_events

from app.config import config
from app.services.calendar_types import (
    CalendarError,
    CalendarNotConnected,
    CalEvent,
    local_tz,
)

log = logging.getLogger("mnemosyne.ics_calendar")

TIMEOUT_SECONDS = 20.0
CACHE_TTL_SECONDS = 300

# url -> (fetched_at, raw bytes). One user, two workspaces; a dict is plenty.
_cache: dict[str, tuple[float, bytes]] = {}


def _url_file(workspace: str) -> Path:
    return config.secrets_path / f"calendar_ics_{workspace}"


def get_url(workspace: str) -> str:
    f = _url_file(workspace)
    if not f.exists():
        return ""
    return f.read_text().strip()


def set_url(workspace: str, url: str) -> None:
    url = url.strip()
    if url.startswith("webcal://"):  # Outlook hands these out
        url = "https://" + url.removeprefix("webcal://")
    if not url.startswith(("https://", "http://")):
        raise CalendarError("That doesn't look like a calendar address (expected an https or webcal link)")
    f = _url_file(workspace)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(url)
    _cache.pop(url, None)


def clear_url(workspace: str) -> None:
    url = get_url(workspace)
    _cache.pop(url, None)
    _url_file(workspace).unlink(missing_ok=True)


async def _fetch(url: str) -> bytes:
    cached = _cache.get(url)
    if cached is not None and time.time() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS, follow_redirects=True) as client:
            resp = await client.get(url)
    except httpx.HTTPError as e:
        raise CalendarError(f"Could not reach the calendar address: {e}") from e
    if resp.status_code >= 400:
        raise CalendarError(f"Calendar address returned {resp.status_code}; the link may have been reset")
    raw = resp.content
    _cache[url] = (time.time(), raw)
    return raw


def _parse(raw: bytes) -> icalendar.Calendar:
    try:
        return icalendar.Calendar.from_ical(raw)
    except ValueError as e:
        raise CalendarError(f"That address didn't return a readable calendar: {e}") from e


def calendar_name(raw: bytes) -> str:
    try:
        cal = _parse(raw)
    except CalendarError:
        return ""
    name = cal.get("X-WR-CALNAME")
    return str(name) if name else ""


async def connected_name(workspace: str) -> str | None:
    """Calendar display name if an ICS URL is stored, else None."""
    url = get_url(workspace)
    if not url:
        return None
    try:
        name = calendar_name(await _fetch(url))
    except CalendarError:
        name = ""
    return name or httpx.URL(url).host or "calendar"


def _event_from(component: icalendar.Event, tz) -> CalEvent | None:
    summary = component.get("SUMMARY")
    title = str(summary) if summary else "(no title)"
    location = str(component.get("LOCATION") or "")
    dtstart = component.get("DTSTART")
    if dtstart is None:
        return None
    start = dtstart.dt
    dtend = component.get("DTEND")
    end = dtend.dt if dtend is not None else None

    if isinstance(start, datetime):
        start = start.astimezone(tz) if start.tzinfo else start.replace(tzinfo=tz)
        if isinstance(end, datetime):
            end = end.astimezone(tz) if end.tzinfo else end.replace(tzinfo=tz)
        else:
            end = None
        return CalEvent(title=title, start=start, end=end, all_day=False, location=location)

    if isinstance(start, date):  # date-only DTSTART means all-day
        return CalEvent(
            title=title,
            start=datetime.combine(start, datetime.min.time(), tzinfo=tz),
            end=None,
            all_day=True,
            location=location,
        )
    return None


async def list_events(workspace: str, time_min: datetime, time_max: datetime) -> list[CalEvent]:
    url = get_url(workspace)
    if not url:
        raise CalendarNotConnected("No calendar address saved for this workspace")
    raw = await _fetch(url)
    cal = _parse(raw)
    tz = local_tz()
    out: list[CalEvent] = []
    # recurring_ical_events expands RRULE/RDATE/EXDATE into concrete
    # occurrences inside the window, which hand-rolled parsing gets wrong.
    for component in recurring_ical_events.of(cal).between(time_min, time_max):
        status = str(component.get("STATUS") or "")
        if status.upper() == "CANCELLED":
            continue
        ev = _event_from(component, tz)
        if ev is not None:
            out.append(ev)
    return out
