"""จัดการระบบ (/admin) — คำขอมัสยิด | รายงาน | สิทธิ์, toggled in the top bar.

Every route here checks its permission on the server (app.permissions.require); hiding the
entry icon on the profile page is only cosmetic. Prayer logs are private and never shown here.
"""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.permissions import ROLE_LABELS, can, require
from app.services import admin_queue, roles
from app.templating import templates

router = APIRouter(tags=["admin"])

VIEWS = ("requests", "reports", "roles")

# ?msg=<code> after a grant/revoke; only known codes are shown, never text from the URL.
MESSAGES = {
    "granted": ("ok", "แต่งตั้งผู้ดูแลระบบแล้ว"),
    "revoked": ("ok", "ถอดผู้ดูแลระบบแล้ว"),
    "bad_email": ("error", "อีเมลไม่ถูกต้อง"),
    "no_user": ("error", "ไม่พบผู้ใช้ที่อีเมลนี้ (ต้องสมัครบัญชีก่อน)"),
    "already": ("error", "ผู้ใช้นี้เป็นผู้ดูแลระบบอยู่แล้ว"),
    "not_found": ("error", "ไม่พบรายการนี้ อาจถูกถอดไปแล้ว"),
    "last_admin": ("error", "ถอดไม่ได้: ต้องมีผู้ดูแลระบบอย่างน้อย 1 คน"),
}


@router.get("/admin")
def admin_panel(
    request: Request,
    view: str = "requests",
    msg: str = "",
    user: User = Depends(require("admin.panel")),
    db: Session = Depends(get_db),
):
    if view not in VIEWS:
        view = "requests"
    admins = roles.list_admins(db) if can(user, "role.manage") else []
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "user": user,
            "active": "profile",
            "view": view,
            "counts": admin_queue.pending_counts(db),
            "admins": admins,
            "role_label": ROLE_LABELS[roles.ADMIN],
            "message": MESSAGES.get(msg),
        },
    )


def _back(msg: str) -> RedirectResponse:
    return RedirectResponse(f"/admin?view=roles&msg={msg}", status_code=303)


@router.post("/admin/roles")
def grant_admin(
    email: str = Form(...),
    user: User = Depends(require("role.manage")),
    db: Session = Depends(get_db),
):
    try:
        roles.grant_admin(db, email, granted_by=user)
    except roles.RoleError as e:
        return _back(e.code)
    return _back("granted")


@router.post("/admin/roles/{role_id}/revoke")
def revoke_admin(
    role_id: int,
    user: User = Depends(require("role.manage")),
    db: Session = Depends(get_db),
):
    try:
        revoked = roles.revoke_admin(db, role_id)
    except roles.RoleError as e:
        return _back(e.code)
    if revoked.id == user.id:
        # removed their own admin role: /admin is now a 404 for them
        return RedirectResponse("/profile", status_code=303)
    return _back("revoked")
