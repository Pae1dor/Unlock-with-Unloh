"""Mosque check-in rules: which prayer a check-in counts for, and when check-in is open.

Prayer times come from our own calculator (praytime_calc) using the MOSQUE's coordinates,
so every mosque in the country gets its local times.

Windows (local time):
  - opens 20 minutes before the adhan (OPENS_BEFORE_ADHAN);
  - closes when the next prayer's time begins; Fajr closes at sunrise; Isha closes at the
    next day's Fajr.
  - Where two windows overlap (the last 20 minutes before an adhan), the upcoming prayer
    wins: someone at the mosque then is there for that prayer.
  - Between sunrise and 20 minutes before Dhuhr nothing is open.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import TIMEZONE
from app.services import praytime_calc
from app.services.aladhan import PRAYERS

OPENS_BEFORE_ADHAN = timedelta(minutes=20)
CHECK_IN_RADIUS_M = 100.0
MAX_ACCURACY_M = 150.0
PRAYER_KEYS = [key for key, _ in PRAYERS]
_LABELS = dict(PRAYERS)
JUMUAH_LABEL = "ญุมอะฮ์"   # Friday Dhuhr (spelling from the project's Islamic terminology glossary)


def prayer_label(prayer_key: str, prayer_date: date) -> str:
    if prayer_key == "Dhuhr" and prayer_date.weekday() == 4:   # Friday
        return JUMUAH_LABEL
    return _LABELS.get(prayer_key, prayer_key)


@dataclass(frozen=True)
class Window:
    prayer_key: str
    prayer_date: date
    adhan: datetime
    opens: datetime
    closes: datetime

    @property
    def label(self) -> str:
        return prayer_label(self.prayer_key, self.prayer_date)


def _times(lat: float, lng: float, day: date, tz: ZoneInfo) -> dict[str, datetime]:
    raw = praytime_calc.calculate(lat, lng, day)
    out = {}
    for key, hhmm in raw.items():
        hh, mm = (int(x) for x in hhmm.split(":"))
        out[key] = datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)
    return out


def _windows(lat: float, lng: float, day: date, tz: ZoneInfo) -> list[Window]:
    today = _times(lat, lng, day, tz)
    tomorrow = _times(lat, lng, day + timedelta(days=1), tz)
    closes = {
        "Fajr": today["Sunrise"],
        "Dhuhr": today["Asr"],
        "Asr": today["Maghrib"],
        "Maghrib": today["Isha"],
        "Isha": tomorrow["Fajr"],
    }
    return [
        Window(key, day, today[key], today[key] - OPENS_BEFORE_ADHAN, closes[key])
        for key in PRAYER_KEYS
    ]


def status_at(lat: float, lng: float, now: datetime) -> tuple[Window | None, Window]:
    """(open window or None, the next window to open after now) for a mosque at lat/lng."""
    tz = ZoneInfo(TIMEZONE)
    now = now.astimezone(tz)
    windows = []
    for offset in (-1, 0, 1):
        windows += _windows(lat, lng, now.date() + timedelta(days=offset), tz)
    open_now = [w for w in windows if w.opens <= now < w.closes]
    current = max(open_now, key=lambda w: w.opens) if open_now else None
    upcoming = min((w for w in windows if w.opens > now), key=lambda w: w.opens)
    return current, upcoming


def now_local() -> datetime:
    return datetime.now(ZoneInfo(TIMEZONE))
