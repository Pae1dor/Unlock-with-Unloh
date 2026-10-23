"""บันทึกละหมาด — mark today's five prayers on /prayer-times, weekly grid on /profile.

Every endpoint works on the logged-in user's own log only; no user id is ever taken from
the request, and logs are never shown on community or other people's pages.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import PrayerLog, User
from app.schemas import PrayerLogIn
from app.services import prayer_log as rules
from app.services import rewards

router = APIRouter(tags=["prayer-log"])


def _fail(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message})


def _owner(user: User | None) -> User:
    if user is None:
        raise _fail(401, "login", "เข้าสู่ระบบเพื่อบันทึกละหมาด")
    return user


def _out(row: PrayerLog, today_count: int) -> dict:
    return {
        "prayer": row.prayer,
        "status": row.status,
        "source": row.source,
        "in_congregation": row.in_congregation,
        "time": rules.local_time(row.logged_at),
        "today_count": today_count,
    }


@router.post("/api/prayer-log")
def log_prayer(
    body: PrayerLogIn,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Mark a prayer as prayed, while its time is open; the server decides, not the client."""
    user = _owner(user)
    now = rules.now_local()
    try:
        row = rules.log_manual(db, user, body.prayer, now)
    except rules.NotYet:
        raise _fail(409, "not_yet", f"ยังไม่เข้าเวลา{rules.LABELS[body.prayer]}") from None
    except rules.Closed:
        raise _fail(409, "closed", f"หมดเวลา{rules.LABELS[body.prayer]}แล้ว หรือยังไม่ถึงเวลาที่บันทึกได้") from None
    return _out(row, len(rules.logs_for_day(db, user.id, row.date)))


@router.get("/api/prayer-log/week")
def prayer_week(
    start: date | None = Query(None, description="any day of the week to show; defaults to this week"),
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = _owner(user)
    now = rules.now_local()
    return week_for(db, user, start or now.date(), now)


def week_for(db: Session, user: User, start: date, now) -> dict:
    """Weekly grid incl. which slots were missed; shared with the profile page."""
    missed_today = [p for p, s in rules.day_states(db, user, now).items() if s["state"] == "missed"]
    return rules.week_summary(db, user.id, start, now.date(),
                              missed_today=missed_today, since=rules._tracking_since(user),
                              windows=rules.open_prayers(user.city, now))


@router.get("/api/prayer-log/alerts")
def prayer_alerts(
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Polled by static/js/ui.js: new missed-prayer notices (each returned once, ever)
    and the prayer whose time is about to run out, if any."""
    if user is None:
        return {"missed": [], "due_soon": None, "rewards": []}
    now = rules.now_local()
    rewards.grant_earned(db, user)
    due = next(({"prayer": p, "label": rules.LABELS[p], "minutes_left": s["minutes_left"]}
                for p, s in rules.day_states(db, user, now).items() if s["state"] == "due_soon"), None)
    return {"missed": rules.new_missed_notices(db, user, now), "due_soon": due,
            "rewards": rewards.take_new_rewards(db, user)}
