"""จัดการระบบ (/admin) — คำขอมัสยิด | รายงาน | สิทธิ์, toggled in the top bar.

Every route here checks its permission on the server (app.permissions.require); hiding the
entry icon on the profile page is only cosmetic. Prayer logs are private and never shown here.
"""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import MosqueRequest, Report, User
from app.permissions import ROLE_LABELS, can, require
from app.services import admin_queue, roles, submissions
from app.templating import templates

router = APIRouter(tags=["admin"])

VIEWS = ("requests", "reports", "roles")

# ?msg=<code> after an admin action; only known codes are shown, never text from the URL.
MESSAGES = {
    "granted": ("ok", "แต่งตั้งผู้ดูแลระบบแล้ว"),
    "revoked": ("ok", "ถอดผู้ดูแลระบบแล้ว"),
    "bad_email": ("error", "อีเมลไม่ถูกต้อง"),
    "no_user": ("error", "ไม่พบผู้ใช้ที่อีเมลนี้ (ต้องสมัครบัญชีก่อน)"),
    "already": ("error", "ผู้ใช้นี้เป็นผู้ดูแลระบบอยู่แล้ว"),
    "not_found": ("error", "ไม่พบรายการนี้ อาจถูกถอดไปแล้ว"),
    "last_admin": ("error", "ถอดไม่ได้: ต้องมีผู้ดูแลระบบอย่างน้อย 1 คน"),
    "approved": ("ok", "อนุมัติแล้ว เพิ่มเข้ารายการมัสยิดของแอป"),
    "rejected": ("ok", "ไม่อนุมัติคำขอแล้ว"),
    "resolved": ("ok", "บันทึกว่าแก้ไขแล้ว"),
    "dismissed": ("ok", "ปิดเรื่องแล้ว"),
    "not_pending": ("error", "คำขอนี้ถูกตรวจไปแล้ว"),
    "not_open": ("error", "เรื่องนี้ถูกปิดไปแล้ว"),
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
    requests = []
    if can(user, "mosque_request.review"):
        rows = db.scalars(select(MosqueRequest).where(MosqueRequest.status == "pending")
                          .order_by(MosqueRequest.created_at)).all()
        # hint for the reviewer: an OSM mosque already within ~50 m (likely a duplicate)
        requests = [(r, submissions.nearest_osm_mosque(r.lat, r.lng)) for r in rows]
    reports = []
    if can(user, "report.review"):
        reports = db.scalars(select(Report).where(Report.status == "open").order_by(Report.created_at)).all()
    return templates.TemplateResponse(
        request,
        "admin.html",
        {
            "user": user,
            "active": "profile",
            "view": view,
            "counts": admin_queue.pending_counts(db),
            "admins": admins,
            "requests": requests,
            "reports": reports,
            "category_labels": submissions.REPORT_CATEGORY_LABELS,
            "role_label": ROLE_LABELS[roles.ADMIN],
            "message": MESSAGES.get(msg),
        },
    )


def _back(msg: str, view: str = "roles") -> RedirectResponse:
    return RedirectResponse(f"/admin?view={view}&msg={msg}", status_code=303)


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


@router.post("/admin/mosque-requests/{request_id}/approve")
def approve_mosque_request(
    request_id: int,
    user: User = Depends(require("mosque_request.review")),
    db: Session = Depends(get_db),
):
    try:
        submissions.approve_request(db, request_id, user)
    except submissions.ReviewError as e:
        return _back(str(e), "requests")
    return _back("approved", "requests")


@router.post("/admin/mosque-requests/{request_id}/reject")
def reject_mosque_request(
    request_id: int,
    note: str = Form(""),
    user: User = Depends(require("mosque_request.review")),
    db: Session = Depends(get_db),
):
    try:
        submissions.reject_request(db, request_id, user, note)
    except submissions.ReviewError as e:
        return _back(str(e), "requests")
    return _back("rejected", "requests")


@router.post("/admin/reports/{report_id}/close")
def close_report(
    report_id: int,
    status: str = Form(...),
    user: User = Depends(require("report.review")),
    db: Session = Depends(get_db),
):
    try:
        submissions.close_report(db, report_id, user, status)
    except submissions.ReviewError as e:
        return _back(str(e), "reports")
    return _back(status, "reports")
