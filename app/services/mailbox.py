"""Mailbox (กล่องจดหมาย): messages from the team, optionally with an outfit gift."""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Mail, User, UserBackgroundUnlock, UserOutfitUnlock
from app.outfits import BACKGROUNDS, OUTFITS


class GiftError(Exception):
    pass


def send(db: Session, user: User, title: str, body: str = "", outfit_key: str | None = None,
         background_key: str | None = None) -> Mail:
    if background_key is not None and background_key not in BACKGROUNDS:
        raise GiftError(f"ไม่มีพื้นหลัง {background_key}")
    if outfit_key is not None:
        outfit = OUTFITS.get(outfit_key)
        if outfit is None:
            raise GiftError(f"ไม่มีชุด {outfit_key}")
        if outfit["gender"] != user.avatar_style:
            raise GiftError(f"ชุด {outfit['name']} ใช้กับตัวละคร {outfit['gender']} แต่ผู้ใช้เป็น {user.avatar_style}")
    mail = Mail(user_id=user.id, title=title.strip(), body=body.strip(),
                gift_outfit_key=outfit_key, gift_background_key=background_key)
    db.add(mail)
    db.commit()
    db.refresh(mail)
    return mail


def inbox(db: Session, user: User) -> list[Mail]:
    return db.scalars(select(Mail).where(Mail.user_id == user.id).order_by(Mail.created_at.desc())).all()


def get_own(db: Session, user: User, mail_id: int) -> Mail | None:
    """Only ever the logged-in user's own mail."""
    return db.scalar(select(Mail).where(Mail.id == mail_id, Mail.user_id == user.id))


def mark_read(db: Session, mail: Mail) -> None:
    if mail.read_at is None:
        mail.read_at = datetime.now(timezone.utc)
        db.commit()


def claim(db: Session, user: User, mail: Mail) -> bool:
    """Unlock the gift for good. False if there is nothing (left) to claim."""
    if not (mail.gift_outfit_key or mail.gift_background_key) or mail.claimed_at is not None:
        return False
    if mail.gift_outfit_key and mail.gift_outfit_key not in user.unlocked_outfits:
        # notified=True: the mailbox itself is the announcement, no extra banner
        db.add(UserOutfitUnlock(user_id=user.id, outfit_key=mail.gift_outfit_key, notified=True))
    if mail.gift_background_key and mail.gift_background_key not in user.owned_backgrounds:
        db.add(UserBackgroundUnlock(user_id=user.id, background_key=mail.gift_background_key))
    mail.claimed_at = datetime.now(timezone.utc)
    mail.read_at = mail.read_at or mail.claimed_at
    try:
        db.commit()
    except IntegrityError:  # already owned through another mail; still mark this one claimed
        db.rollback()
        mail.claimed_at = datetime.now(timezone.utc)
        db.commit()
    db.refresh(user)
    return True
