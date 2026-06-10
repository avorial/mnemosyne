"""Google Calendar client — OAuth authorization-code flow + events.

Auth: standard web-app flow. The refresh token is the durable credential,
stored at config.google_token_file. Access tokens are re-minted on expiry.

Setup (one-time, in Google Cloud Console):
- Create an OAuth client of type "Web application".
- Add {BASE_URL}/widgets/calendar/google/callback as an authorized redirect URI.
- Put the client id/secret in GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any

import httpx

from app.config import config
from app.services import oauth_store
from app.services.calendar_types import (
    CalendarError,
    CalendarNotConnected,
    CalEvent,
    local_tz,
)

log = logging.getLogger("mnemosyne.google_calendar")

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
EVENTS_URL = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
PRIMARY_URL = "https://www.googleapis.com/calendar/v3/calendars/primary"
SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
TIMEOUT_SECONDS = 15.0


def redirect_uri() -> str:
    return f"{config.base_url}/widgets/calendar/google/callback"


def auth_url(state: str) -> str:
    params = httpx.QueryParams(
        {
            "client_id": config.google_client_id,
            "redirect_uri": redirect_uri(),
            "response_type": "code",
            "scope": SCOPE,
            "access_type": "offline",
            # Force the consent screen so Google re-issues a refresh token
            # even if the app was authorized before.
            "prompt": "consent",
            "state": state,
        }
    )
    return f"{AUTH_URL}?{params}"


async def _token_request(form: dict[str, str]) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        resp = await client.post(TOKEN_URL, data=form)
    if resp.status_code >= 400:
        raise CalendarError(f"Google token endpoint → {resp.status_code}: {resp.text[:300]}")
    return resp.json()


async def exchange_code(code: str) -> oauth_store.TokenSet:
    data = await _token_request(
        {
            "code": code,
            "client_id": config.google_client_id,
            "client_secret": config.google_client_secret,
            "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code",
        }
    )
    refresh = data.get("refresh_token", "")
    if not refresh:
        raise CalendarError("Google returned no refresh token; revoke the app's access and reconnect")
    tokens = oauth_store.TokenSet(
        access_token=data["access_token"],
        refresh_token=refresh,
        expires_at=int(time.time()) + int(data.get("expires_in", 3600)),
    )
    tokens.account = await _account_label(tokens.access_token)
    oauth_store.save(config.google_token_file, tokens)
    return tokens


async def _account_label(access_token: str) -> str:
    """The primary calendar's id is the account email. Best-effort."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.get(
                PRIMARY_URL, headers={"Authorization": f"Bearer {access_token}"}
            )
        if resp.status_code < 400:
            return resp.json().get("id", "")
    except httpx.HTTPError:
        pass
    return ""


async def _valid_access_token() -> str:
    tokens = oauth_store.load(config.google_token_file)
    if tokens is None or not tokens.refresh_token:
        raise CalendarNotConnected("Google Calendar is not connected")
    if not tokens.access_expired:
        return tokens.access_token
    try:
        data = await _token_request(
            {
                "refresh_token": tokens.refresh_token,
                "client_id": config.google_client_id,
                "client_secret": config.google_client_secret,
                "grant_type": "refresh_token",
            }
        )
    except CalendarError as e:
        # invalid_grant means the refresh token was revoked or expired:
        # the connection is gone, not merely errored.
        if "invalid_grant" in str(e):
            oauth_store.clear(config.google_token_file)
            raise CalendarNotConnected("Google access was revoked; reconnect") from e
        raise
    tokens.access_token = data["access_token"]
    tokens.expires_at = int(time.time()) + int(data.get("expires_in", 3600))
    oauth_store.save(config.google_token_file, tokens)
    return tokens.access_token


def connected_account() -> str | None:
    tokens = oauth_store.load(config.google_token_file)
    if tokens is None or not tokens.refresh_token:
        return None
    return tokens.account or "connected"


def disconnect() -> None:
    oauth_store.clear(config.google_token_file)


def _parse_event(item: dict[str, Any]) -> CalEvent | None:
    tz = local_tz()
    start = item.get("start") or {}
    end = item.get("end") or {}
    title = item.get("summary") or "(no title)"
    location = item.get("location") or ""
    if "date" in start:  # all-day
        d = datetime.fromisoformat(start["date"])
        return CalEvent(
            title=title,
            start=d.replace(tzinfo=tz),
            end=None,
            all_day=True,
            location=location,
        )
    if "dateTime" in start:
        s = datetime.fromisoformat(start["dateTime"]).astimezone(tz)
        e = None
        if "dateTime" in end:
            e = datetime.fromisoformat(end["dateTime"]).astimezone(tz)
        return CalEvent(title=title, start=s, end=e, all_day=False, location=location)
    return None


async def list_events(time_min: datetime, time_max: datetime) -> list[CalEvent]:
    token = await _valid_access_token()
    params = {
        "timeMin": time_min.isoformat(),
        "timeMax": time_max.isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "50",
    }
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        resp = await client.get(
            EVENTS_URL, params=params, headers={"Authorization": f"Bearer {token}"}
        )
    if resp.status_code >= 400:
        raise CalendarError(f"Google events → {resp.status_code}: {resp.text[:300]}")
    out: list[CalEvent] = []
    for item in resp.json().get("items", []):
        if item.get("status") == "cancelled":
            continue
        ev = _parse_event(item)
        if ev is not None:
            out.append(ev)
    return out
