"""Shared calendar types — provider clients normalize into CalEvent."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import config


class CalendarError(RuntimeError):
    pass


class CalendarNotConnected(CalendarError):
    """No stored token, or the refresh token was revoked upstream."""


@dataclass
class CalEvent:
    title: str
    start: datetime        # tz-aware, in the configured local timezone
    end: datetime | None
    all_day: bool
    location: str = ""

    @property
    def time_label(self) -> str:
        if self.all_day:
            return "all day"
        s = _clock(self.start)
        if self.end is None:
            return s
        return f"{s}–{_clock(self.end)}"


def local_tz() -> ZoneInfo:
    return ZoneInfo(config.timezone)


def _clock(dt: datetime) -> str:
    h = dt.hour % 12 or 12
    suffix = "a" if dt.hour < 12 else "p"
    if dt.minute == 0:
        return f"{h}{suffix}"
    return f"{h}:{dt.minute:02d}{suffix}"
