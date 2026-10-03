"""เพิ่มมัสยิด — users ask for a missing mosque; admins review it at /admin."""
import math

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import MosqueRequest, User
from app.services import submissions
from app.templating import templates

router = APIRouter(tags=["mosque-requests"])

TRI_STATE = {"yes": True, "no": False}   # anything else = not sure (None)


def _form_page(request: Request, db: Session, user: User, form: dict, error: str | None, status: int = 200):
    return templates.TemplateResponse(
        request,
        "mosque_request_form.html",
        {
            "user": user,
            "active": "profile",
            "back_url": "/profile",
            "form": form,
            "error": error,
            "remaining": max(0, submissions.DAILY_LIMIT - submissions.submitted_today(db, user.id)),
        },
        status_code=status,
    )


@router.get("/mosque-requests/new")
def new_request_form(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    return _form_page(request, db, user, {"women": "unknown", "jumuah": "unknown"}, None)


@router.post("/mosque-requests/new")
def create_request(
    request: Request,
    name: str = Form(""),
    lat: str = Form(""),
    lng: str = Form(""),
    address: str = Form(""),
    opening_hours: str = Form(""),
    women: str = Form("unknown"),
    jumuah: str = Form("unknown"),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    form = {
        "name": name.strip()[:200], "lat": lat, "lng": lng,
        "address": address.strip()[:400], "opening_hours": opening_hours.strip()[:200],
        "women": women if women in TRI_STATE else "unknown",
        "jumuah": jumuah if jumuah in TRI_STATE else "unknown",
    }

    def fail(message: str):
        return _form_page(request, db, user, form, message, status=400)

    if not form["name"]:
        return fail("กรุณากรอกชื่อมัสยิด")
    # lat/lng only ever come from the pin (hidden fields filled by static/js/pin-picker.js)
    try:
        lat_f, lng_f = float(lat), float(lng)
    except ValueError:
        return fail("กรุณาปักหมุดตำแหน่งมัสยิดบนแผนที่")
    if not (math.isfinite(lat_f) and math.isfinite(lng_f)) or not submissions.in_thailand(lat_f, lng_f):
        return fail("ตำแหน่งที่ปักต้องอยู่ในประเทศไทย")
    try:
        submissions.check_daily_limit(db, user)
    except submissions.SubmitError as e:
        return fail(e.message)

    db.add(MosqueRequest(
        user_id=user.id, name=form["name"], lat=round(lat_f, 7), lng=round(lng_f, 7),
        address=form["address"], opening_hours=form["opening_hours"],
        has_women_area=TRI_STATE.get(form["women"]), has_jumuah=TRI_STATE.get(form["jumuah"]),
    ))
    db.commit()
    return RedirectResponse("/mosque-requests/mine?sent=1", status_code=303)


@router.get("/mosque-requests/mine")
def my_requests(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(MosqueRequest).where(MosqueRequest.user_id == user.id).order_by(MosqueRequest.created_at.desc())
    ).all()
    return templates.TemplateResponse(
        request,
        "mosque_request_mine.html",
        {
            "user": user,
            "active": "profile",
            "back_url": "/mosque-requests/new",
            "rows": rows,
            "status_labels": submissions.REQUEST_STATUS_LABELS,
            "sent": request.query_params.get("sent") == "1",
        },
    )
