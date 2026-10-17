"""บันทึกละหมาด — mark today's five prayers on /prayer-times, weekly grid on /profile.

Every endpoint works on the logged-in user's own log only; no user id is ever taken from
the request, and logs are never shown on community or other people's pages.
"""
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_user
from app.models import PrayerLog, User
from app.schemas import PrayerLogIn
from app.services import prayer_log as rules
from app.services import rewards
from app.templating import templates

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
    """Mark one of today's prayers as prayed; on time / qada is decided here, not by the client."""
    user = _owner(user)
    now = rules.now_local()
    try:
        row = rules.log_manual(db, user, body.prayer, now)
    except rules.NotYet:
        raise _fail(409, "not_yet", f"ยังไม่เข้าเวลา{rules.LABELS[body.prayer]}") from None
    return _out(row, len(rules.logs_for_day(db, user.id, now.date())))


@router.delete("/api/prayer-log/{prayer}")
def undo_prayer(
    prayer: str,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The toast's ยกเลิก: removes today's manual log of that prayer."""
    user = _owner(user)
    if prayer not in rules.PRAYER_KEYS:
        raise _fail(404, "unknown_prayer", "ไม่พบเวลาละหมาดนี้")
    today = rules.now_local().date()
    if not rules.undo_manual(db, user, prayer, today):
        raise _fail(409, "cannot_undo", "ยกเลิกรายการนี้ไม่ได้")
    return {"prayer": prayer, "today_count": len(rules.logs_for_day(db, user.id, today))}


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
                              missed_today=missed_today, since=rules._tracking_since(user))


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
    yesterday = rules.yesterday_status(db, user, now)
    return {"missed": rules.new_missed_notices(db, user, now), "due_soon": due,
            "rewards": rewards.take_new_rewards(db, user),
            # non-empty -> ui.js shows the "เมื่อวานคุณได้ละหมาดไหม" pop-up (can't be dismissed)
            "yesterday_pending": [{"prayer": p["key"], "label": p["label"]}
                                  for p in (yesterday["pending"] if yesterday else [])]}


@router.get("/prayer-log/yesterday")
def yesterday_page(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    """Answer for yesterday's unlogged prayers: prayed (forgot to log) or didn't pray."""
    return templates.TemplateResponse(request, "prayer_yesterday.html", {
        "user": user, "active": "home", "back_url": "/prayer-times",
        "day": rules.yesterday_status(db, user, rules.now_local()),
        "done": request.query_params.get("done") == "1",
    })


@router.post("/prayer-log/yesterday")
async def yesterday_answer(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    form = await request.form()
    answers = {key[len("answer_"):]: str(value) for key, value in form.items() if key.startswith("answer_")}
    rules.answer_yesterday(db, user, rules.now_local(), answers)
    return RedirectResponse("/prayer-log/yesterday?done=1", status_code=303)
