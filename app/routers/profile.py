"""บัญชี — profile view and edit."""
from urllib.parse import quote

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import CITY_COOKIE
from app.database import get_db
from app.deps import get_current_user, require_user
from app.models import Donation, ForumPost, User, UserBackground, UserOutfit
from app.outfits import BACKGROUNDS, DEFAULT_BACKGROUND, OUTFITS, RARITY_LABELS, backgrounds_list, outfits_for
from app.permissions import can
from app.services import admin_queue, prayer_log
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
    today = prayer_log.now_local().date()
    return templates.TemplateResponse(
        request,
        "profile.html",
        {
            "user": user,
            "active": "profile",
            "post_count": post_count,
            "donation_count": donation_count,
            "saved": request.query_params.get("saved") == "1",
            # weekly prayer grid (read-only); the arrows fetch other weeks from /api/prayer-log/week
            "prayer_week": prayer_log.week_summary(db, user.id, today, today),
            # None hides the admin icon; a number is the badge (things waiting for review)
            "admin_pending": admin_queue.pending_counts(db)["total"] if can(user, "admin.panel") else None,
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


@router.get("/profile/outfits")
def wardrobe(request: Request, user: User | None = Depends(get_current_user)):
    avatar_style = user.avatar_style if user else "male"
    return templates.TemplateResponse(
        request,
        "wardrobe.html",
        {
            "user": user,
            "active": "profile",
            "back_url": "/profile" if user else "/",
            "outfits": outfits_for(avatar_style),
            "rarity_labels": RARITY_LABELS,
            "backgrounds": backgrounds_list(),
            "background": user.background if user else {"key": DEFAULT_BACKGROUND, **BACKGROUNDS[DEFAULT_BACKGROUND]},
            "saved": request.query_params.get("saved") == "1",
        },
    )


@router.post("/profile/outfit")
def equip_outfit(
    outfit_key: str = Form(""),
    background_key: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    if background_key in BACKGROUNDS:
        if user.background_choice is None:
            user.background_choice = UserBackground(background_key=background_key)
        else:
            user.background_choice.background_key = background_key

    outfit = OUTFITS.get(outfit_key)
    if outfit is None or outfit["gender"] != user.avatar_style:
        # "" (or anything unknown) = back to the plain 2D mascot
        user.outfit_choice = None
    elif user.outfit_choice is None:
        user.outfit_choice = UserOutfit(outfit_key=outfit_key)
    else:
        user.outfit_choice.outfit_key = outfit_key
    db.commit()
    return RedirectResponse("/profile/outfits?saved=1", status_code=303)
