"""Promote an existing user to admin (can create news posts).

Run with:  python -m app.make_admin someone@example.com
"""
import sys

from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models import User


def make_admin(email: str) -> None:
    init_db()
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == email.strip().lower()))
        if user is None:
            print(f"ไม่พบผู้ใช้ที่อีเมล {email}")
            sys.exit(1)
        user.is_admin = True
        db.commit()
        print(f"ตั้ง {user.full_name} ({user.email}) เป็นแอดมินแล้ว")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("ใช้งาน: python -m app.make_admin <email>")
        sys.exit(1)
    make_admin(sys.argv[1])
