"""บัญชี — profile view and edit."""
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import CITY_COOKIE
from app.database import get_db
from app.deps import require_user
from app.models import Donation, ForumPost, User
from app.templating import AVATAR_STYLE_KEYS, templates

router = APIRouter(tags=["profile"])


@router.get("/profile")
def profile(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    post_count = db.scalar(select(func.count(ForumPost.id)).where(ForumPost.user_id == user.id)) or 0
    donation_count = db.scalar(select(func.count(Donation.id)).where(Donation.user_id == user.id)) or 0
    return templates.TemplateResponse(
        request,
        "profile.html",
        {
            "user": user,
            "active": "profile",
            "post_count": post_count,
            "donation_count": donation_count,
            "saved": request.query_params.get("saved") == "1",
        },
    )


@router.post("/profile")
def update_profile(
    full_name: str = Form(...),
    city: str = Form(""),
    phone: str = Form(""),
    avatar_style: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if full_name.strip():
        user.full_name = full_name.strip()
    user.city = city.strip() or user.city
    user.phone = phone.strip() or None
    if avatar_style in AVATAR_STYLE_KEYS:
        user.avatar_style = avatar_style
    db.commit()

    response = RedirectResponse("/profile?saved=1", status_code=303)
    # Keep the prayer-time city in sync with the profile.
    response.set_cookie(CITY_COOKIE, quote(user.city), max_age=60 * 60 * 24 * 365, path="/")
    return response
