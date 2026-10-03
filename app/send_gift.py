"""Send a mailbox message with an outfit gift to a user.

Run with:  python -m app.send_gift someone@example.com <item_key> "ชื่อของขวัญ" ["ข้อความ"]
item_key is an outfit (OUTFITS, e.g. street-flame, musalli) or a background (BACKGROUNDS,
e.g. haram) from app/outfits.py.
"""
import sys

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models import User
from app.outfits import BACKGROUNDS
from app.services.mailbox import GiftError, send


def main(email: str, item_key: str, title: str, body: str = "") -> None:
    init_db()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email.strip().lower()))
        if user is None:
            print(f"ไม่พบผู้ใช้ที่อีเมล {email}")
            sys.exit(1)
        try:
            if item_key in BACKGROUNDS:
                mail = send(db, user, title, body, background_key=item_key)
            else:
                mail = send(db, user, title, body, outfit_key=item_key)
        except GiftError as exc:
            print(f"ส่งไม่สำเร็จ: {exc}")
            sys.exit(1)
        print(f"ส่ง \"{mail.title}\" ({item_key}) ให้ {user.full_name} ({user.email}) แล้ว — mail id {mail.id}")


if __name__ == "__main__":
    if len(sys.argv) not in (4, 5):
        print('ใช้งาน: python -m app.send_gift <email> <item_key> "ชื่อของขวัญ" ["ข้อความ"]')
        sys.exit(1)
    main(*sys.argv[1:])
