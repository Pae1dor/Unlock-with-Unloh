"""เวลาละหมาด — full day's prayer times, plus the per-prayer notification settings."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_city, get_current_user, require_user
from app.models import User
from app.services.aladhan import PRAYERS, get_prayer_times
from app.templating import templates

router = APIRouter(tags=["prayer"])

# api-key -> the User column that holds that prayer's notification toggle.
NOTIFY_FIELDS = {
    "Fajr": "notify_fajr",
    "Dhuhr": "notify_dhuhr",
    "Asr": "notify_asr",
    "Maghrib": "notify_maghrib",
    "Isha": "notify_isha",
}


@router.get("/api/prayer-status")
def prayer_status(city: str = Depends(get_city)):
    """Lightweight JSON poll so pages can move the 'current prayer' highlight
    and the 'ละหมาดถัดไป' countdown live, without a full page reload."""
    prayer = get_prayer_times(city)
    next_item = next((t for t in prayer["timings"] if t["key"] == prayer["next"]), None)
    return {
        "ok": prayer["ok"],
        "current": prayer["current"],
        "next": prayer["next"],
        "next_name": next_item["name_th"] if next_item else None,
        "next_time": next_item["time"] if next_item else None,
    }


@router.get("/prayer-times")
def prayer_times(
    request: Request,
    user: User | None = Depends(get_current_user),
    city: str = Depends(get_city),
):
    prayer = get_prayer_times(city)
    return templates.TemplateResponse(
        request,
        "prayer_times.html",
        {"user": user, "active": "home", "city": city, "prayer": prayer},
    )


@router.get("/notifications")
def notification_settings(request: Request, user: User = Depends(require_user)):
    return templates.TemplateResponse(
        request,
        "notifications.html",
        {
            "user": user,
            "active": "profile",
            "prayers": PRAYERS,
            "saved": request.query_params.get("saved") == "1",
        },
    )


@router.post("/notifications")
def update_notification_settings(
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
    notify_fajr: str | None = Form(None),
    notify_dhuhr: str | None = Form(None),
    notify_asr: str | None = Form(None),
    notify_maghrib: str | None = Form(None),
    notify_isha: str | None = Form(None),
):
    user.notify_fajr = notify_fajr is not None
    user.notify_dhuhr = notify_dhuhr is not None
    user.notify_asr = notify_asr is not None
    user.notify_maghrib = notify_maghrib is not None
    user.notify_isha = notify_isha is not None
    db.commit()
    return RedirectResponse("/notifications?saved=1", status_code=303)
