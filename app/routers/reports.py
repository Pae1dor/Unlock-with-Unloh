"""แจ้งปัญหา — users report bugs, wrong mosque data, inappropriate content or ideas.

The app version and the page the user came from are attached automatically. An attached
image is private: only its sender and admins can open it (GET /reports/{id}/image).
"""
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import APP_VERSION
from app.database import get_db
from app.deps import require_user
from app.models import Report, User
from app.permissions import can
from app.services import submissions
from app.templating import templates

router = APIRouter(tags=["reports"])

MAX_DETAIL = 2000


def _came_from(request: Request) -> str:
    """Path of the page that linked here (same site only), e.g. "/profile"."""
    referer = request.headers.get("referer") or ""
    parts = urlsplit(referer)
    if not parts.path.startswith("/") or parts.netloc != request.url.netloc:
        return ""
    path = parts.path + (f"?{parts.query}" if parts.query else "")
    return "" if parts.path.startswith("/reports/") else path[:300]


def _clean_page(page: str) -> str:
    page = page.strip()[:300]
    return page if page.startswith("/") and not page.startswith("//") else ""


def _form_page(request: Request, db: Session, user: User, form: dict, error: str | None, status: int = 200):
    return templates.TemplateResponse(
        request,
        "report_form.html",
        {
            "user": user,
            "active": "profile",
            "back_url": "/profile",
            "form": form,
            "error": error,
            "categories": submissions.REPORT_CATEGORIES,
            "app_version": APP_VERSION,
            "remaining": max(0, submissions.DAILY_LIMIT - submissions.submitted_today(db, user.id)),
        },
        status_code=status,
    )


@router.get("/reports/new")
def new_report_form(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    return _form_page(request, db, user, {"category": "", "detail": "", "page": _came_from(request)}, None)


@router.post("/reports/new")
def create_report(
    request: Request,
    category: str = Form(""),
    detail: str = Form(""),
    page: str = Form(""),
    image: UploadFile | None = File(None),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    form = {"category": category, "detail": detail.strip()[:MAX_DETAIL], "page": _clean_page(page)}

    def fail(message: str):
        return _form_page(request, db, user, form, message, status=400)

    if category not in submissions.REPORT_CATEGORY_LABELS:
        return fail("กรุณาเลือกหมวดของเรื่องที่แจ้ง")
    if not form["detail"]:
        return fail("กรุณาเล่ารายละเอียด")
    try:
        submissions.check_daily_limit(db, user)   # before touching the upload
        image_name = None
        if image is not None and image.filename:
            # sync route (runs in a worker thread), so read the spooled file directly
            data = image.file.read(submissions.MAX_UPLOAD_BYTES + 1)
            if data:
                image_name = submissions.save_report_image(data)
    except submissions.SubmitError as e:
        return fail(e.message)

    db.add(Report(
        user_id=user.id, category=category, detail=form["detail"], image_name=image_name,
        app_version=APP_VERSION, page=form["page"],
    ))
    db.commit()
    return RedirectResponse("/reports/mine?sent=1", status_code=303)


@router.get("/reports/mine")
def my_reports(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Report).where(Report.user_id == user.id).order_by(Report.created_at.desc())).all()
    return templates.TemplateResponse(
        request,
        "report_mine.html",
        {
            "user": user,
            "active": "profile",
            "back_url": "/reports/new",
            "rows": rows,
            "category_labels": submissions.REPORT_CATEGORY_LABELS,
            "status_labels": submissions.REPORT_STATUS_LABELS,
            "sent": request.query_params.get("sent") == "1",
        },
    )


@router.get("/reports/{report_id}/image")
def report_image(report_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    report = db.get(Report, report_id)
    # same 404 whether the report doesn't exist or isn't yours: don't reveal which
    if report is None or not report.image_name or (report.user_id != user.id and not can(user, "report.review")):
        raise HTTPException(status_code=404)
    path = (submissions.REPORT_IMAGE_DIR / report.image_name).resolve()
    if path.parent != submissions.REPORT_IMAGE_DIR.resolve() or not path.is_file():
        raise HTTPException(status_code=404)
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})
