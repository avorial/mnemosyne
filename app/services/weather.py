"""Weather via Open-Meteo — no API key, no account, true zero-setup.

Setup is typing a place name once: the free geocoding endpoint resolves it
to coordinates, which persist in the settings table. Forecasts cache for
ten minutes.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import datetime

import httpx

from app import db
from app.services.calendar_types import local_tz

log = logging.getLogger("mnemosyne.weather")

GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
TIMEOUT_SECONDS = 15.0
CACHE_TTL_SECONDS = 600
SETTINGS_KEY = "weather_location"

_cache: dict[str, tuple[float, dict]] = {}


class WeatherError(RuntimeError):
    pass


@dataclass(frozen=True)
class Location:
    name: str       # "Lehi, Utah"
    latitude: float
    longitude: float


# WMO weather interpretation codes, compressed to glance words.
_CODE_WORDS = [
    ((0,), "clear"),
    ((1, 2), "partly cloudy"),
    ((3,), "overcast"),
    ((45, 48), "fog"),
    ((51, 53, 55, 56, 57), "drizzle"),
    ((61, 63, 65, 66, 67), "rain"),
    ((71, 73, 75, 77), "snow"),
    ((80, 81, 82), "showers"),
    ((85, 86), "snow showers"),
    ((95, 96, 99), "thunderstorms"),
]


def describe(code: int) -> str:
    for codes, word in _CODE_WORDS:
        if code in codes:
            return word
    return ""


def get_location() -> Location | None:
    with db.connect() as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key = ?", (SETTINGS_KEY,)
        ).fetchone()
    if row is None:
        return None
    try:
        d = json.loads(row["value"])
        return Location(name=d["name"], latitude=d["latitude"], longitude=d["longitude"])
    except (json.JSONDecodeError, KeyError):
        return None


def _save_location(loc: Location) -> None:
    payload = json.dumps({"name": loc.name, "latitude": loc.latitude, "longitude": loc.longitude})
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (SETTINGS_KEY, payload),
        )


def clear_location() -> None:
    with db.connect() as conn:
        conn.execute("DELETE FROM settings WHERE key = ?", (SETTINGS_KEY,))
    _cache.clear()


async def set_location_by_name(query: str) -> Location:
    query = query.strip()
    if not query:
        raise WeatherError("Type a place name")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.get(GEOCODE_URL, params={"name": query, "count": 1})
    except httpx.HTTPError as e:
        raise WeatherError(f"Could not reach the geocoder: {e}") from e
    if resp.status_code >= 400:
        raise WeatherError(f"Geocoder returned {resp.status_code}")
    results = resp.json().get("results") or []
    if not results:
        raise WeatherError(f"No place found for {query!r}")
    r = results[0]
    label = ", ".join(p for p in (r.get("name"), r.get("admin1")) if p)
    loc = Location(name=label or query, latitude=r["latitude"], longitude=r["longitude"])
    _save_location(loc)
    _cache.clear()
    return loc


async def forecast() -> dict:
    """Glance payload: current, today, tomorrow, next hours. Cached 10 min."""
    loc = get_location()
    if loc is None:
        raise WeatherError("No location set")
    key = f"{loc.latitude},{loc.longitude}"
    cached = _cache.get(key)
    if cached is not None and time.time() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]

    params = {
        "latitude": loc.latitude,
        "longitude": loc.longitude,
        "current": "temperature_2m,apparent_temperature,weather_code",
        "hourly": "temperature_2m,precipitation_probability,weather_code",
        "daily": "temperature_2m_max,temperature_2m_min,weather_code,precipitation_probability_max",
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "auto",
        "forecast_days": 2,
    }
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_SECONDS) as client:
            resp = await client.get(FORECAST_URL, params=params)
    except httpx.HTTPError as e:
        raise WeatherError(f"Could not reach Open-Meteo: {e}") from e
    if resp.status_code >= 400:
        raise WeatherError(f"Open-Meteo returned {resp.status_code}")
    raw = resp.json()

    current = raw.get("current") or {}
    daily = raw.get("daily") or {}
    hourly = raw.get("hourly") or {}

    tz = local_tz()
    now = datetime.now(tz)
    hours = []
    times = hourly.get("time") or []
    for i, t in enumerate(times):
        dt = datetime.fromisoformat(t).replace(tzinfo=tz)
        if dt <= now:
            continue
        h = dt.hour % 12 or 12
        hours.append(
            {
                "label": f"{h}{'a' if dt.hour < 12 else 'p'}",
                "temp": round(hourly["temperature_2m"][i]),
                "precip": hourly.get("precipitation_probability", [None] * len(times))[i],
            }
        )
        if len(hours) >= 6:
            break

    def _day(i: int) -> dict:
        return {
            "hi": round(daily["temperature_2m_max"][i]),
            "lo": round(daily["temperature_2m_min"][i]),
            "word": describe(daily["weather_code"][i]),
            "precip": (daily.get("precipitation_probability_max") or [None, None])[i],
        }

    out = {
        "location": loc.name,
        "now": {
            "temp": round(current.get("temperature_2m", 0)),
            "feels": round(current.get("apparent_temperature", 0)),
            "word": describe(current.get("weather_code", -1)),
        },
        "today": _day(0),
        "tomorrow": _day(1),
        "hours": hours,
    }
    _cache[key] = (time.time(), out)
    return out
