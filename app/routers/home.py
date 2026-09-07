"""หน้าแรก — greeting, dates, prayer strip and the 8 quick-action grid."""
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import CITY_COOKIE, DEFAULT_CITY
from app.database import get_db
from app.deps import get_city, get_current_user
from app.models import News, User
from app.services.aladhan import get_prayer_times, greeting_for, now_local
from app.templating import templates

router = APIRouter(tags=["home"])

QUICK_ACTIONS = [
    {"label": "อัลกุรอาน", "url": "/quran", "icon": "book"},
    {"label": "เวลาละหมาด", "url": "/prayer-times", "icon": "clock"},
    {"label": "บริจาค", "url": "/donation", "icon": "heart"},
    {"label": "ค้นหามัสยิด", "url": "/mosques", "icon": "map-pin"},
    {"label": "ข่าวสาร", "url": "/news", "icon": "newspaper"},
    {"label": "ภาษาอิหม่าม", "url": "/community", "icon": "users"},
    {"label": "อาลิม", "url": "/news?category=article", "icon": "mosque"},
    {"label": "ทั้งหมด", "url": "/community", "icon": "grid"},
]


@router.get("/")
def home(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
    city: str = Depends(get_city),
):
    now = now_local()
    prayer = get_prayer_times(city)
    latest_news = db.scalars(select(News).order_by(News.published_at.desc()).limit(3)).all()

    return templates.TemplateResponse(
        request,
        "home.html",
        {
            "user": user,
            "active": "home",
            "city": city,
            "greeting": greeting_for(now),
            "prayer": prayer,
            "quick_actions": QUICK_ACTIONS,
            "latest_news": latest_news,
        },
    )


@router.post("/set-city")
def set_city(city: str = Form(...), next: str = Form("/")):
    """Persist the chosen city in a cookie; used for prayer times and Hijri date."""
    target = next if next.startswith("/") and not next.startswith("//") else "/"
    response = RedirectResponse(target, status_code=303)
    response.set_cookie(CITY_COOKIE, quote(city.strip() or DEFAULT_CITY), max_age=60 * 60 * 24 * 365, path="/")
    return response
