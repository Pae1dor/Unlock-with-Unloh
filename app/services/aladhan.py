"""Prayer times + Hijri date from the free Aladhan API.

https://api.aladhan.com/v1/timingsByCity — no API key required.
Responses are cached in-process, keyed by (city, date), so we hit the network at
most once per city per day. If Aladhan is unreachable, times for Thai provinces are
calculated locally (app/services/praytime_calc.py) until it comes back.
"""
from __future__ import annotations

import time
from datetime import date, datetime
from zoneinfo import ZoneInfo

import httpx

from app.config import COUNTRY, TIMEZONE
from app.services import praytime_calc

API_URL = "https://api.aladhan.com/v1/timingsByCity"
# 3 = Muslim World League, the method commonly used in Thailand.
METHOD = 3

# The five obligatory prayers, in order, with their Thai labels.
PRAYERS: list[tuple[str, str]] = [
    ("Fajr", "ฟัจร์"),
    ("Dhuhr", "ซุฮ์รี"),
    ("Asr", "อัสรี"),
    ("Maghrib", "มัฆริบ"),
    ("Isha", "อิชาอ์"),
]

HIJRI_MONTHS_TH = {
    1: "มุฮัรรอม",
    2: "เศาะฟัร",
    3: "รอบีอุลเอาวัล",
    4: "รอบีอุษษานี",
    5: "ญุมาดัลอูลา",
    6: "ญุมาดัลอาคิเราะฮ์",
    7: "เราะญับ",
    8: "ชะอ์บาน",
    9: "เราะมะฎอน",
    10: "เชาวาล",
    11: "ซุลเกาะดะฮ์",
    12: "ซุลฮิจญะฮ์",
}

THAI_MONTHS = [
    "มกราคม", "กุมภาพันธ์", "มีนาคม", "เมษายน", "พฤษภาคม", "มิถุนายน",
    "กรกฎาคม", "สิงหาคม", "กันยายน", "ตุลาคม", "พฤศจิกายน", "ธันวาคม",
]

THAI_WEEKDAYS = ["วันจันทร์", "วันอังคาร", "วันพุธ", "วันพฤหัสบดี", "วันศุกร์", "วันเสาร์", "วันอาทิตย์"]

_cache: dict[tuple[str, str], dict] = {}

REQUEST_TIMEOUT = 6.0
OUTAGE_RETRY_SECONDS = 60
# key -> (monotonic time of the failed attempt, the fallback result we returned)
_outage: dict[tuple[str, str], tuple[float, dict]] = {}


def now_local() -> datetime:
    return datetime.now(ZoneInfo(TIMEZONE))


def thai_date(d: date) -> str:
    """e.g. 'วันเสาร์ที่ 5 กันยายน 2569' (Buddhist era, as used in Thailand)."""
    return f"{THAI_WEEKDAYS[d.weekday()]}ที่ {d.day} {THAI_MONTHS[d.month - 1]} {d.year + 543}"


def greeting_for(dt: datetime) -> str:
    hour = dt.hour
    if hour < 12:
        return "สวัสดีตอนเช้า"
    if hour < 16:
        return "สวัสดีตอนบ่าย"
    if hour < 19:
        return "สวัสดีตอนเย็น"
    return "สวัสดีตอนค่ำ"


def _fallback(city: str, error: str) -> dict:
    return {
        "ok": False,
        "error": error,
        "city": city,
        "timings": [],
        "hijri": "",
        "gregorian": thai_date(now_local().date()),
        "current": None,
        "next": None,
    }


def _format_hijri(hijri: dict) -> str:
    try:
        day = int(hijri["day"])
        month = int(hijri["month"]["number"])
        year = hijri["year"]
        return f"{day} {HIJRI_MONTHS_TH.get(month, hijri['month']['en'])} {year} ฮ.ศ."
    except (KeyError, TypeError, ValueError):
        return ""


def _mark_current(timings: list[dict], ref: datetime) -> tuple[str | None, str | None]:
    """Return (current_prayer_key, next_prayer_key) based on the local clock."""
    minutes_now = ref.hour * 60 + ref.minute
    current = None
    nxt = None
    for item in timings:
        hh, mm = item["time"].split(":")
        item_minutes = int(hh) * 60 + int(mm)
        if item_minutes <= minutes_now:
            current = item["key"]
        elif nxt is None:
            nxt = item["key"]
    if current is None:
        # Before Fajr — the previous day's Isha is still "current".
        current = timings[-1]["key"] if timings else None
    if nxt is None:
        nxt = timings[0]["key"] if timings else None
    return current, nxt


def _calculated(city: str, day: date) -> dict | None:
    """Times computed on our side, for when Aladhan is down. None if the city is unknown."""
    coords = praytime_calc.coordinates_for(city)
    if coords is None:
        return None
    raw = praytime_calc.calculate(*coords, day)
    timings = [{"key": k, "name_th": label, "time": raw[k]} for k, label in PRAYERS]
    current, nxt = _mark_current(timings, now_local())
    return {
        "ok": True,
        "error": None,
        "calculated": True,
        "city": city,
        "timings": timings,
        # Hijri is left out on purpose: a local calendar can be a day off from the announced one.
        "hijri": "",
        "gregorian": thai_date(day),
        "current": current,
        "next": nxt,
        "sunrise": raw["Sunrise"],
    }


def get_prayer_times(city: str, on: date | None = None) -> dict:
    """Fetch (and cache) the day's prayer times for a city.

    Always returns a dict; on network failure `ok` is False and `error` carries a
    Thai message suitable for showing to the visitor.
    """
    day = on or now_local().date()
    key = (city.strip().lower(), day.isoformat())
    if key in _cache:
        cached = _cache[key]
        # Recompute the current/next marker so a cached day still tracks the clock.
        cached["current"], cached["next"] = _mark_current(cached["timings"], now_local())
        return cached

    # While the API is down, don't re-hit it on every page view (each attempt blocks the
    # request for up to the timeout, and home/prayer/mosque pages all call this).
    failed = _outage.get(key)
    if failed and time.monotonic() - failed[0] < OUTAGE_RETRY_SECONDS:
        result = failed[1]
        if result["ok"]:
            result["current"], result["next"] = _mark_current(result["timings"], now_local())
        return result

    params = {
        "city": city,
        "country": COUNTRY,
        "method": METHOD,
        "date": day.strftime("%d-%m-%Y"),
    }
    try:
        # follow_redirects is required: Aladhan answers timingsByCity with a 302.
        response = httpx.get(API_URL, params=params, timeout=REQUEST_TIMEOUT, follow_redirects=True)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        result = _calculated(city, day) or _fallback(
            city, "ไม่สามารถเชื่อมต่อข้อมูลเวลาละหมาดได้ กรุณาลองใหม่อีกครั้ง"
        )
        _outage[key] = (time.monotonic(), result)
        return result
    _outage.pop(key, None)

    data = payload.get("data") or {}
    raw_timings = data.get("timings") or {}
    if not raw_timings:
        return _fallback(city, f"ไม่พบข้อมูลเวลาละหมาดสำหรับ “{city}” กรุณาตรวจสอบชื่อเมือง")

    timings = []
    for api_key, thai_label in PRAYERS:
        value = raw_timings.get(api_key)
        if not value:
            continue
        timings.append({"key": api_key, "name_th": thai_label, "time": value.split(" ")[0]})

    if not timings:
        return _fallback(city, f"ไม่พบข้อมูลเวลาละหมาดสำหรับ “{city}”")

    current, nxt = _mark_current(timings, now_local())
    result = {
        "ok": True,
        "error": None,
        "city": city,
        "timings": timings,
        "hijri": _format_hijri((data.get("date") or {}).get("hijri") or {}),
        "gregorian": thai_date(day),
        "current": current,
        "next": nxt,
        "sunrise": (raw_timings.get("Sunrise") or "").split(" ")[0],
    }
    _cache[key] = result
    return result
