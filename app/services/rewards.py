"""Outfit rewards: earn outfits from the prayer log (catalog: app/outfits.py, "unlock").

five_prayers — all five prayers logged on the same day, any day, from any source
(listening to the Quran, a mosque check-in, ...).
"""
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import PrayerLog, User, UserOutfitUnlock
from app.outfits import OUTFITS
from app.services.prayer_log import PRAYER_KEYS


def has_full_day(db: Session, user_id: int) -> bool:
    day = db.scalar(
        select(PrayerLog.date)
        .where(PrayerLog.user_id == user_id)
        .group_by(PrayerLog.date)
        .having(func.count(PrayerLog.id) >= len(PRAYER_KEYS))
        .limit(1)
    )
    return day is not None


CONDITIONS = {
    "five_prayers": has_full_day,
}


def grant_earned(db: Session, user: User) -> None:
    """Unlock every outfit whose condition the user now meets (idempotent)."""
    have = user.unlocked_outfits
    for key, outfit in OUTFITS.items():
        rule = outfit.get("unlock")
        if not rule or key in have or rule not in CONDITIONS:
            continue
        if CONDITIONS[rule](db, user.id):
            db.add(UserOutfitUnlock(user_id=user.id, outfit_key=key))
            try:
                db.commit()
            except IntegrityError:  # another tab granted it first
                db.rollback()
    db.refresh(user)


def take_new_rewards(db: Session, user: User) -> list[dict]:
    """Newly earned outfits not announced yet; each is returned once, then marked notified."""
    rows = db.scalars(select(UserOutfitUnlock).where(
        UserOutfitUnlock.user_id == user.id, UserOutfitUnlock.notified.is_(False))).all()
    out = []
    for row in rows:
        row.notified = True
        outfit = OUTFITS.get(row.outfit_key)
        if outfit:
            out.append({"key": row.outfit_key, "name": outfit["name"], "image": outfit["image"]})
    if rows:
        db.commit()
    return out
