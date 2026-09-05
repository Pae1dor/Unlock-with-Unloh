"""เวลาละหมาด — full day's prayer times plus the notification toggle."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_city, get_current_user, require_user
from app.models import User
from app.schemas import PrayerNotificationIn, PrayerNotificationOut
from app.services.aladhan import get_prayer_times
from app.templating import templates

router = APIRouter(tags=["prayer"])


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
        {
            "user": user,
            "active": "home",
            "city": city,
            "prayer": prayer,
            "notifications_enabled": user.prayer_notifications_enabled if user else False,
        },
    )


@router.post("/api/prayer-notifications", response_model=PrayerNotificationOut)
def set_prayer_notifications(
    payload: PrayerNotificationIn,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    user.prayer_notifications_enabled = payload.enabled
    db.commit()
    return PrayerNotificationOut(enabled=user.prayer_notifications_enabled)
