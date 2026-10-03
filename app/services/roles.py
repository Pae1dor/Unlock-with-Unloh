"""Granting and revoking the system-wide admin role (used by /admin and app/make_admin.py).

The system must never be left without an admin: revoking the last system-wide admin is
refused. The admin rows are locked (SELECT ... FOR UPDATE on PostgreSQL) before counting,
so two admins revoking each other at the same moment cannot both succeed. SQLite runs
one write at a time anyway, and SQLAlchemy leaves FOR UPDATE out there.
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import User, UserRole

ADMIN = "admin"


class RoleError(Exception):
    """A refused grant/revoke; `code` maps to a Thai message in the caller."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _global_admins(db: Session, lock: bool = False) -> list[UserRole]:
    query = select(UserRole).where(UserRole.role == ADMIN, UserRole.mosque_id.is_(None))
    if lock:
        query = query.with_for_update()
    return list(db.scalars(query).all())


def list_admins(db: Session) -> list[UserRole]:
    rows = _global_admins(db)
    return sorted(rows, key=lambda r: r.created_at)


def grant_admin(db: Session, email: str, granted_by: User | None) -> UserRole:
    email = email.strip().lower()
    if "@" not in email:
        raise RoleError("bad_email")
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        raise RoleError("no_user")
    if any(r.user_id == user.id for r in _global_admins(db)):
        raise RoleError("already")

    row = UserRole(user_id=user.id, role=ADMIN, mosque_id=None,
                   granted_by=granted_by.id if granted_by else None)
    db.add(row)
    user.is_admin = True   # keep the legacy flag in step
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise RoleError("already") from None
    db.refresh(row)
    return row


def revoke_admin(db: Session, role_id: int) -> User:
    admins = _global_admins(db, lock=True)
    row = next((r for r in admins if r.id == role_id), None)
    if row is None:
        db.rollback()
        raise RoleError("not_found")
    if len(admins) <= 1:
        db.rollback()
        raise RoleError("last_admin")
    user = row.user
    db.delete(row)
    user.is_admin = False
    db.commit()
    return user


def revoke_admin_by_email(db: Session, email: str) -> User:
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    row = next((r for r in _global_admins(db) if user and r.user_id == user.id), None)
    if row is None:
        raise RoleError("not_admin")
    return revoke_admin(db, row.id)


def backfill_from_legacy_flag(db: Session) -> int:
    """First run only: users flagged is_admin before user_roles existed become admins.

    Skipped once any system-wide admin row exists, so a later revoke is never undone
    by a restart (and the last admin can't be revoked, so it never runs again).
    """
    if _global_admins(db):
        return 0
    users = db.scalars(select(User).where(User.is_admin.is_(True))).all()
    for user in users:
        db.add(UserRole(user_id=user.id, role=ADMIN, mosque_id=None, granted_by=None))
    db.commit()
    return len(users)
