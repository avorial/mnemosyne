"""Microsoft 365 calendar client — OAuth authorization-code flow + Graph calendarView.

Auth: Microsoft identity platform v2.0 endpoints, delegated Calendars.Read.
The refresh token (granted via the offline_access scope) is the durable
credential, stored at config.ms_token_file.

Setup (one-time, in Entra admin center → App registrations):
- Register a web app; add {BASE_URL}/widgets/calendar/ms/callback as a
  Web redirect URI.
- Add delegated permissions: Calendars.Read, offline_access, User.Read.
- Create a client secret. Put id/secret/tenant in MS_CLIENT_ID /
  MS_CLIENT_SECRET / MS_TENANT_ID.
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

log = logging.getLogger("mnemosyne.ms_calendar")

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPE = "offline_access https://graph.microsoft.com/Calendars.Read https://graph.microsoft.com/User.Read"
TIMEOUT_SECONDS = 15.0


def _login_base() -> str:
    return f"https://login.microsoftonline.com/{config.ms_tenant_id}/oauth2/v2.0"


def redirect_uri() -> str:
    return f"{config.base_url}/widgets/calendar/ms/callback"


def auth_url(state: str) -> str:
    params = httpx.QueryParams(
        {
            "client_id": config.ms_client_id,
            "redirect_uri": redirect_uri(),
            "response_type": "code",
            "response_mode": "query",
            "scope": SCOPE,
            "state": state,
        }
    )
    return f"{_login_base()}/authorize?{params}"


async def _token_request(form: dict[str, str]) -> dict:
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        resp = await client.post(f"{_login_base()}/token", data=form)
    if resp.status_code >= 400:
        raise CalendarError(f"Microsoft token endpoint → {resp.status_code}: {resp.text[:300]}")
    return resp.json()


async def exchange_code(code: str) -> oauth_store.TokenSet:
    data = await _token_request(
        {
            "code": code,
            "client_id": config.ms_client_id,
            "client_secret": config.ms_client_secret,
            "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code",
            "scope": SCOPE,
        }
    )
    refresh = data.get("refresh_token", "")
    if not refresh:
        raise CalendarError("Microsoft returned no refresh token; is offline_access consented?")
    tokens = oauth_store.TokenSet(
        access_token=data["access_token"],
        refresh_token=refresh,
        expires_at=int(time.time()) + int(data.get("expires_in", 3600)),
    )
    tokens.account = await _account_label(tokens.access_token)
    oauth_store.save(config.ms_token_file, tokens)
    return tokens


async def _account_label(access_token: str) -> str:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.get(
                f"{GRAPH}/me?$select=userPrincipalName,mail",
                headers={"Authorization": f"Bearer {access_token}"},
            )
        if resp.status_code < 400:
            d = resp.json()
            return d.get("mail") or d.get("userPrincipalName") or ""
    except httpx.HTTPError:
        pass
    return ""


async def _valid_access_token() -> str:
    tokens = oauth_store.load(config.ms_token_file)
    if tokens is None or not tokens.refresh_token:
        raise CalendarNotConnected("Work calendar is not connected")
    if not tokens.access_expired:
        return tokens.access_token
    try:
        data = await _token_request(
            {
                "refresh_token": tokens.refresh_token,
                "client_id": config.ms_client_id,
                "client_secret": config.ms_client_secret,
                "grant_type": "refresh_token",
                "scope": SCOPE,
            }
        )
    except CalendarError as e:
        if "invalid_grant" in str(e):
            oauth_store.clear(config.ms_token_file)
            raise CalendarNotConnected("Microsoft access was revoked; reconnect") from e
        raise
    tokens.access_token = data["access_token"]
    # Microsoft rotates refresh tokens; keep the newest one.
    tokens.refresh_token = data.get("refresh_token", tokens.refresh_token)
    tokens.expires_at = int(time.time()) + int(data.get("expires_in", 3600))
    oauth_store.save(config.ms_token_file, tokens)
    return tokens.access_token


def connected_account() -> str | None:
    tokens = oauth_store.load(config.ms_token_file)
    if tokens is None or not tokens.refresh_token:
        return None
    return tokens.account or "connected"


def disconnect() -> None:
    oauth_store.clear(config.ms_token_file)


def _parse_event(item: dict[str, Any]) -> CalEvent | None:
    tz = local_tz()
    title = item.get("subject") or "(no title)"
    location = ((item.get("location") or {}).get("displayName")) or ""
    all_day = bool(item.get("isAllDay"))
    start_raw = ((item.get("start") or {}).get("dateTime")) or ""
    end_raw = ((item.get("end") or {}).get("dateTime")) or ""
    if not start_raw:
        return None
    # With the Prefer: outlook.timezone header, Graph returns naive local
    # strings like 2026-06-10T09:00:00.0000000 (fromisoformat truncates the
    # extra fractional digits on 3.11+).
    start = datetime.fromisoformat(start_raw).replace(tzinfo=tz)
    end = datetime.fromisoformat(end_raw).replace(tzinfo=tz) if end_raw else None
    if all_day:
        return CalEvent(title=title, start=start, end=None, all_day=True, location=location)
    return CalEvent(title=title, start=start, end=end, all_day=False, location=location)


async def list_events(time_min: datetime, time_max: datetime) -> list[CalEvent]:
    token = await _valid_access_token()
    params = {
        "startDateTime": time_min.isoformat(),
        "endDateTime": time_max.isoformat(),
        "$orderby": "start/dateTime",
        "$top": "50",
        "$select": "subject,start,end,isAllDay,location,isCancelled",
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Prefer": f'outlook.timezone="{config.timezone}"',
    }
    async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
        resp = await client.get(f"{GRAPH}/me/calendarView", params=params, headers=headers)
    if resp.status_code >= 400:
        raise CalendarError(f"Graph calendarView → {resp.status_code}: {resp.text[:300]}")
    out: list[CalEvent] = []
    for item in resp.json().get("value", []):
        if item.get("isCancelled"):
            continue
        ev = _parse_event(item)
        if ev is not None:
            out.append(ev)
    return out
