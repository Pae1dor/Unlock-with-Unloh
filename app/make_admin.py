"""Grant or revoke the system-wide admin role (ผู้ดูแลระบบ) from the command line.

The first admin is set up this way; after that admins can also be managed at /admin.
The user must already have an account (register first). Revoking the last admin is refused.

Run with:  python -m app.make_admin someone@example.com
           python -m app.make_admin --revoke someone@example.com
"""
import sys

from app.database import SessionLocal, init_db
from app.services import roles

MESSAGES = {
    "bad_email": "อีเมลไม่ถูกต้อง",
    "no_user": "ไม่พบผู้ใช้ที่อีเมลนี้ (ต้องสมัครบัญชีก่อน)",
    "already": "ผู้ใช้นี้เป็นผู้ดูแลระบบอยู่แล้ว",
    "not_admin": "ผู้ใช้นี้ไม่ได้เป็นผู้ดูแลระบบ",
    "last_admin": "ถอดไม่ได้: ต้องมีผู้ดูแลระบบอย่างน้อย 1 คน",
}


def main(argv: list[str]) -> int:
    revoke = "--revoke" in argv
    args = [a for a in argv if a != "--revoke"]
    if len(args) != 1:
        print("ใช้งาน: python -m app.make_admin [--revoke] <email>")
        return 1

    init_db()
    with SessionLocal() as db:
        try:
            if revoke:
                user = roles.revoke_admin_by_email(db, args[0])
                print(f"ถอด {user.full_name} ({user.email}) ออกจากผู้ดูแลระบบแล้ว")
            else:
                row = roles.grant_admin(db, args[0], granted_by=None)
                print(f"ตั้ง {row.user.full_name} ({row.user.email}) เป็นผู้ดูแลระบบแล้ว")
        except roles.RoleError as e:
            print(MESSAGES.get(e.code, e.code))
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
