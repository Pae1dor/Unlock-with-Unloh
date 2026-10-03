"""Prayer log rules: when each of the five prayers is "on time", and the weekly summary.

Times are the same ones the prayer-times page shows (aladhan.get_prayer_times, which
falls back to praytime_calc) for the city in the user's profile.

On time = from the prayer's own time until the next one begins:
  Fajr -> sunrise, Dhuhr -> Asr, Asr -> Maghrib, Maghrib -> Isha, Isha -> next day's Fajr.
Logged after that = qada. (Fajr ends at sunrise, not at Dhuhr, as in services/checkin.py.)

A log is private: every query here is filtered by the caller's user id, and nothing in this
module takes a user id from the client.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import TIMEZONE
from app.models import MosqueCheckin, PrayerLog, PrayerNotice, User
from app.services import praytime_calc
from app.services.aladhan import PRAYERS, get_prayer_times

# lowercase keys stored in prayer_log.prayer, in order; API_KEYS maps to "Fajr" etc.
PRAYER_KEYS = [key.lower() for key, _ in PRAYERS]
API_KEYS = {key.lower(): key for key, _ in PRAYERS}
LABELS = {key.lower(): label for key, label in PRAYERS}

THAI_WEEKDAYS_SHORT = ["จ", "อ", "พ", "พฤ", "ศ", "ส", "อา"]
THAI_MONTHS_SHORT = ["ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
                     "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."]


def now_local() -> datetime:
    return datetime.now(ZoneInfo(TIMEZONE))


def _utc(dt: datetime) -> datetime:
    # Stored in UTC like every other timestamp; SQLite drops the offset, so it must be UTC.
    return dt.astimezone(timezone.utc)


def local_time(dt: datetime) -> str:
    """'HH:MM' local time of a stored timestamp (naive values from SQLite are UTC)."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(ZoneInfo(TIMEZONE)).strftime("%H:%M")


def same_city(a: str | None, b: str | None) -> bool:
    """True when two city names mean the same place ("Bangkok" == "กรุงเทพมหานคร")."""
    if not a or not b:
        return False
    ca, cb = praytime_calc.coordinates_for(a), praytime_calc.coordinates_for(b)
    if ca is not None and cb is not None:
        return ca == cb
    return a.strip().lower() == b.strip().lower()


def _day_times(city: str, day: date) -> dict[str, datetime] | None:
    """{"Fajr": dt, ..., "Sunrise": dt} for a city and day, or None if times are unavailable."""
    tz = ZoneInfo(TIMEZONE)
    prayer = get_prayer_times(city, day)
    raw = {t["key"]: t["time"] for t in prayer.get("timings") or []}
    if prayer.get("sunrise"):
        raw["Sunrise"] = prayer["sunrise"]
    if len(raw) < 6:
        coords = praytime_calc.coordinates_for(city)
        if coords is None:
            return None
        raw = praytime_calc.calculate(*coords, day)
    out = {}
    for key, hhmm in raw.items():
        try:
            hh, mm = (int(x) for x in hhmm.split(":")[:2])
        except ValueError:
            return None
        out[key] = datetime(day.year, day.month, day.day, hh, mm, tzinfo=tz)
    return out


def start_times(city: str, day: date) -> dict[str, datetime] | None:
    """When each prayer's time begins on `day` (keys: fajr..isha)."""
    times = _day_times(city, day)
    if times is None:
        return None
    return {key: times[API_KEYS[key]] for key in PRAYER_KEYS}


def end_time(city: str, day: date, prayer: str) -> datetime | None:
    """When the on-time window for `prayer` on `day` closes."""
    if prayer == "isha":
        tomorrow = _day_times(city, day + timedelta(days=1))
        return tomorrow["Fajr"] if tomorrow else None
    times = _day_times(city, day)
    if times is None:
        return None
    nxt = {"fajr": "Sunrise", "dhuhr": "Asr", "asr": "Maghrib", "maghrib": "Isha"}[prayer]
    return times[nxt]


def status_for(city: str, day: date, prayer: str, at: datetime) -> str:
    end = end_time(city, day, prayer)
    # Times unavailable (unknown city and Aladhan down): don't mark anyone late on a guess.
    if end is None:
        return "on_time"
    return "on_time" if at < end else "qada"


def logs_for_day(db: Session, user_id: int, day: date) -> dict[str, PrayerLog]:
    rows = db.scalars(select(PrayerLog).where(PrayerLog.user_id == user_id, PrayerLog.date == day)).all()
    return {r.prayer: r for r in rows}


class NotYet(Exception):
    """The prayer's time has not begun yet."""


def log_manual(db: Session, user: User, prayer: str, now: datetime) -> PrayerLog:
    """Mark today's `prayer` as prayed. Tapping again returns the existing record."""
    day = now.date()
    starts = start_times(user.city, day)
    if starts is not None and now < starts[prayer]:
        raise NotYet()

    existing = logs_for_day(db, user.id, day).get(prayer)
    if existing is not None:
        return existing

    row = PrayerLog(
        user_id=user.id,
        date=day,
        prayer=prayer,
        logged_at=_utc(now),
        status=status_for(user.city, day, prayer, now),
        source="manual",
        in_congregation=False,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # double tap raced itself; the first insert won
        db.rollback()
        return logs_for_day(db, user.id, day)[prayer]
    db.refresh(row)
    return row


def current_prayer(city: str, now: datetime) -> tuple[date, str] | None:
    """(day, prayer) whose on-time window contains `now`, or None (e.g. sunrise -> Dhuhr).

    Before today's Fajr it is still the previous day's Isha.
    """
    day = now.date()
    starts = start_times(city, day)
    if starts is None:
        return None
    if now < starts["fajr"]:
        return day - timedelta(days=1), "isha"
    for prayer in reversed(PRAYER_KEYS):
        if now >= starts[prayer]:
            end = end_time(city, day, prayer)
            if end is not None and now >= end:
                return None
            return day, prayer
    return None


def log_listen(db: Session, user: User, now: datetime) -> tuple[PrayerLog, bool] | None:
    """Listening to the Quran during a prayer's time ticks that prayer (source "quran").

    Returns (row, created) or None when no prayer's time is running. Never touches a row
    that already exists (manual, check-in or an earlier listen).
    """
    current = current_prayer(user.city, now)
    if current is None:
        return None
    day, prayer = current
    existing = logs_for_day(db, user.id, day).get(prayer)
    if existing is not None:
        return existing, False

    row = PrayerLog(
        user_id=user.id,
        date=day,
        prayer=prayer,
        logged_at=_utc(now),
        status="on_time",  # inside the window by definition
        source="quran",
        in_congregation=False,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return logs_for_day(db, user.id, day)[prayer], False
    db.refresh(row)
    return row, True


DUE_SOON_MINUTES = 30


def _tracking_since(user: User) -> date:
    """Days before the account existed are never "missed"."""
    created = user.created_at
    if created.tzinfo is None:
        created = created.replace(tzinfo=timezone.utc)
    return created.astimezone(ZoneInfo(TIMEZONE)).date()


def day_states(db: Session, user: User, now: datetime) -> dict[str, dict]:
    """Today's unlogged prayers that are missed (time over) or due soon (< 30 min left).

    {"asr": {"state": "missed"}, "maghrib": {"state": "due_soon", "minutes_left": 12}}
    Prayers that are logged, not started yet, or comfortably open are left out.
    """
    day = now.date()
    if day < _tracking_since(user):
        return {}
    starts = start_times(user.city, day)
    if starts is None:
        return {}
    logs = logs_for_day(db, user.id, day)
    joined = user.created_at if user.created_at.tzinfo else user.created_at.replace(tzinfo=timezone.utc)
    out = {}
    for prayer in PRAYER_KEYS:
        if prayer in logs or now < starts[prayer]:
            continue
        end = end_time(user.city, day, prayer)
        # no end time, or its time was already over before the account existed
        if end is None or end <= joined:
            continue
        if now >= end:
            out[prayer] = {"state": "missed"}
        elif end - now <= timedelta(minutes=DUE_SOON_MINUTES):
            out[prayer] = {"state": "due_soon", "minutes_left": max(1, int((end - now).total_seconds() // 60))}
    return out


def missed_since(db: Session, user: User, now: datetime) -> list[tuple[date, str]]:
    """Missed prayers that may still need a notice: today's, plus yesterday's Isha
    (its time runs until this morning's Fajr)."""
    missed = [(now.date(), p) for p, s in day_states(db, user, now).items() if s["state"] == "missed"]
    yesterday = now.date() - timedelta(days=1)
    starts = start_times(user.city, now.date())
    if (
        yesterday >= _tracking_since(user)
        and starts is not None
        and now >= starts["fajr"]
        and "isha" not in logs_for_day(db, user.id, yesterday)
    ):
        missed.append((yesterday, "isha"))
    return missed


def new_missed_notices(db: Session, user: User, now: datetime) -> list[dict]:
    """Record a notice for every missed prayer not noticed before; return only the new ones.

    Honours the per-prayer switches on /notifications. The unique constraint keeps it to
    one notice per prayer even if two tabs ask at the same moment.
    """
    created = []
    for day, prayer in missed_since(db, user, now):
        if not getattr(user, f"notify_{prayer}", True):
            continue
        exists = db.scalar(select(PrayerNotice.id).where(
            PrayerNotice.user_id == user.id, PrayerNotice.date == day, PrayerNotice.prayer == prayer))
        if exists:
            continue
        db.add(PrayerNotice(user_id=user.id, date=day, prayer=prayer))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        created.append({"date": day.isoformat(), "prayer": prayer, "label": LABELS[prayer],
                        "yesterday": day != now.date()})
    return created


def undo_manual(db: Session, user: User, prayer: str, day: date) -> bool:
    """Remove a manual log of today's `prayer` (the toast's ยกเลิก). Check-in logs stay."""
    row = logs_for_day(db, user.id, day).get(prayer)
    if row is None or row.source != "manual":
        return False
    db.delete(row)
    db.commit()
    return True


def record_checkin(db: Session, user: User, checkin: MosqueCheckin, at: datetime) -> None:
    """A mosque check-in counts as that prayer, prayed in congregation.

    Replaces a manual log of the same prayer instead of adding a second row.
    """
    prayer = checkin.prayer_key.lower()
    if prayer not in API_KEYS:
        return
    day = checkin.prayer_date
    starts = start_times(user.city, day)
    # Check-in opens 20 minutes before the adhan: someone at the mosque then is early, not late.
    if starts is not None and at < starts[prayer]:
        status = "on_time"
    else:
        status = status_for(user.city, day, prayer, at)

    for _ in range(2):
        row = logs_for_day(db, user.id, day).get(prayer)
        if row is None:
            row = PrayerLog(user_id=user.id, date=day, prayer=prayer)
            db.add(row)
        row.logged_at = _utc(at)
        row.status = status
        row.source = "checkin"
        row.in_congregation = True
        row.mosque_id = checkin.osm_id
        try:
            db.commit()
            return
        except IntegrityError:
            # a manual tap landed in between; loop once more and update that row instead
            db.rollback()


def streak(db: Session, user_id: int, today: date) -> int:
    """Days in a row with all five prayers logged, up to today.

    Today only counts once it is complete; until then the streak runs to yesterday,
    so an unfinished day never shows the streak as broken.
    """
    full_days = db.scalars(
        select(PrayerLog.date)
        .where(PrayerLog.user_id == user_id, PrayerLog.date <= today)
        .group_by(PrayerLog.date)
        .having(func.count(PrayerLog.id) >= len(PRAYER_KEYS))
        .order_by(PrayerLog.date.desc())
        .limit(3660)
    ).all()
    full = set(full_days)
    day = today if today in full else today - timedelta(days=1)
    count = 0
    while day in full:
        count += 1
        day -= timedelta(days=1)
    return count


def week_start(day: date) -> date:
    return day - timedelta(days=day.weekday())   # Monday


def _short_date(d: date) -> str:
    return f"{d.day} {THAI_MONTHS_SHORT[d.month - 1]}"


def week_summary(db: Session, user_id: int, start: date, today: date,
                 missed_today: list[str] | None = None, since: date | None = None) -> dict:
    """Grid data for the profile card: 7 days (Mon-Sun) x 5 prayers, plus totals."""
    start = week_start(start)
    current = week_start(today)
    if start > current:
        start = current
    end = start + timedelta(days=6)

    rows = db.scalars(
        select(PrayerLog).where(PrayerLog.user_id == user_id, PrayerLog.date >= start, PrayerLog.date <= end)
    ).all()
    # Mosque names live on the check-in row (one per user, prayer and day).
    names = {
        (c.prayer_date, c.prayer_key.lower()): c.mosque_name
        for c in db.scalars(
            select(MosqueCheckin).where(
                MosqueCheckin.user_id == user_id,
                MosqueCheckin.prayer_date >= start,
                MosqueCheckin.prayer_date <= end,
            )
        ).all()
    }
    by_key = {(r.date, r.prayer): r for r in rows}

    days = []
    for i in range(7):
        d = start + timedelta(days=i)
        cells = {}
        for p in PRAYER_KEYS:
            r = by_key.get((d, p))
            if r is None:
                cells[p] = None
                continue
            cells[p] = {
                "status": r.status,
                "source": r.source,
                "in_congregation": r.in_congregation,
                "time": local_time(r.logged_at),
                "mosque_name": names.get((d, p)) if r.source == "checkin" else None,
            }
        if d < today and (since is None or d >= since):
            missed = [p for p in PRAYER_KEYS if cells[p] is None]
        elif d == today:
            missed = [p for p in (missed_today or []) if cells[p] is None]
        else:
            missed = []
        days.append({
            "missed": missed,
            "date": d.isoformat(),
            "weekday": THAI_WEEKDAYS_SHORT[i],
            "day": d.day,
            "label": f"{THAI_WEEKDAYS_SHORT[i]}. {_short_date(d)}",
            "is_today": d == today,
            "is_future": d > today,
            "prayers": cells,
        })

    year = end.year + 543
    return {
        "start": start.isoformat(),
        "range": f"{_short_date(start)} – {_short_date(end)} {year}",
        "total": len(rows),
        "max": 7 * len(PRAYER_KEYS),
        "streak": streak(db, user_id, today),
        "prev": (start - timedelta(days=7)).isoformat(),
        "next": (start + timedelta(days=7)).isoformat() if start < current else None,
        "prayers": [{"key": p, "label": LABELS[p]} for p in PRAYER_KEYS],
        "days": days,
    }
