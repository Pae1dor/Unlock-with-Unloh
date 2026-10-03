"""จัดการระบบ (/admin) — คำขอมัสยิด | รายงาน | สิทธิ์, toggled in the top bar.

Every route here checks its permission on the server (app.permissions.require); hiding the
entry icon on the profile page is only cosmetic. Prayer logs are private and never shown here.
"""
import math

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AppMosque, MosqueRequest, Report, User
from app.permissions import ROLE_LABELS, can, require
from app.services import admin_queue, app_mosques, roles, submissions
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
    "mosque_saved": ("ok", "บันทึกข้อมูลมัสยิดแล้ว"),
    "mosque_hidden": ("ok", "ซ่อนมัสยิดจากแผนที่แล้ว ประวัติเช็คอินเดิมยังอยู่ครบ"),
    "mosque_shown": ("ok", "แสดงมัสยิดบนแผนที่อีกครั้งแล้ว"),
}

TRI_STATE = {"yes": True, "no": False}   # anything else = not sure (None)


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
    approved = []
    if can(user, "mosque.manage"):
        approved = db.scalars(select(AppMosque).order_by(AppMosque.is_active.desc(), AppMosque.created_at.desc())).all()
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
            "approved": approved,
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


# ---------- mosques added through the app (never deleted: check-ins point at "app:<id>") ----------

def _mosque_or_404(db: Session, mosque_id: int) -> AppMosque:
    row = db.get(AppMosque, mosque_id)
    if row is None:
        raise HTTPException(status_code=404)
    return row


def _tri(value: bool | None) -> str:
    return "yes" if value is True else "no" if value is False else "unknown"


def _edit_page(request: Request, user: User, row: AppMosque, form: dict, error: str | None, status: int = 200):
    return templates.TemplateResponse(
        request,
        "admin_app_mosque.html",
        {"user": user, "active": "profile", "back_url": "/admin?view=requests",
         "mosque": row, "form": form, "error": error},
        status_code=status,
    )


@router.get("/admin/app-mosques/{mosque_id}")
def edit_app_mosque_form(
    request: Request,
    mosque_id: int,
    user: User = Depends(require("mosque.manage")),
    db: Session = Depends(get_db),
):
    row = _mosque_or_404(db, mosque_id)
    form = {"name": row.name, "lat": row.lat, "lng": row.lng, "address": row.address,
            "opening_hours": row.opening_hours, "women": _tri(row.has_women_area), "jumuah": _tri(row.has_jumuah)}
    return _edit_page(request, user, row, form, None)


@router.post("/admin/app-mosques/{mosque_id}")
def edit_app_mosque(
    request: Request,
    mosque_id: int,
    name: str = Form(""),
    lat: str = Form(""),
    lng: str = Form(""),
    address: str = Form(""),
    opening_hours: str = Form(""),
    women: str = Form("unknown"),
    jumuah: str = Form("unknown"),
    user: User = Depends(require("mosque.manage")),
    db: Session = Depends(get_db),
):
    row = _mosque_or_404(db, mosque_id)
    form = {"name": name.strip()[:200], "lat": lat, "lng": lng, "address": address.strip()[:400],
            "opening_hours": opening_hours.strip()[:200],
            "women": women if women in TRI_STATE else "unknown", "jumuah": jumuah if jumuah in TRI_STATE else "unknown"}
    if not form["name"]:
        return _edit_page(request, user, row, form, "กรุณากรอกชื่อมัสยิด", 400)
    try:
        lat_f, lng_f = float(lat), float(lng)
    except ValueError:
        return _edit_page(request, user, row, form, "กรุณาปักหมุดตำแหน่งมัสยิดบนแผนที่", 400)
    if not (math.isfinite(lat_f) and math.isfinite(lng_f)) or not submissions.in_thailand(lat_f, lng_f):
        return _edit_page(request, user, row, form, "ตำแหน่งที่ปักต้องอยู่ในประเทศไทย", 400)

    moved = (round(lat_f, 7), round(lng_f, 7)) != (round(row.lat, 7), round(row.lng, 7))
    row.name, row.address, row.opening_hours = form["name"], form["address"], form["opening_hours"]
    row.has_women_area, row.has_jumuah = TRI_STATE.get(form["women"]), TRI_STATE.get(form["jumuah"])
    if moved:
        row.lat, row.lng = round(lat_f, 7), round(lng_f, 7)
        row.osm_ref = app_mosques.match_osm(row.lat, row.lng)   # it may now stand in for another OSM pin
    db.commit()
    return _back("mosque_saved", "requests")


@router.post("/admin/app-mosques/{mosque_id}/visibility")
def set_app_mosque_visibility(
    mosque_id: int,
    active: str = Form(...),
    user: User = Depends(require("mosque.manage")),
    db: Session = Depends(get_db),
):
    """Hide (or show again) on the map. The row stays: check-ins and prayer logs refer to it."""
    row = _mosque_or_404(db, mosque_id)
    row.is_active = active == "1"
    db.commit()
    return _back("mosque_shown" if row.is_active else "mosque_hidden", "requests")
