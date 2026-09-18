"""ค้นหามัสยิด — Leaflet map, distance-sorted list, and the mosque detail page
(today's prayer times, upcoming activities, and the 'ฉันไปด้วย' RSVP for the next prayer)."""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_city, get_current_user, require_user
from app.models import Mosque, MosqueAttendance, MosqueEvent, User
from app.schemas import MosqueOut
from app.services.aladhan import get_prayer_times, now_local
from app.templating import templates

router = APIRouter(tags=["mosques"])


@router.get("/mosques")
def mosque_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    mosques = db.scalars(select(Mosque).order_by(Mosque.name)).all()
    return templates.TemplateResponse(
        request,
        "mosques.html",
        {"user": user, "active": "home", "mosques": mosques},
    )


def _next_prayer_attendance(db: Session, mosque_id: int, prayer_key: str | None):
    """Who's RSVP'd ('ฉันไปด้วย') for this mosque's next prayer today."""
    if not prayer_key:
        return [], 0
    today = now_local().date()
    attendees = db.scalars(
        select(User)
        .join(MosqueAttendance, MosqueAttendance.user_id == User.id)
        .where(
            MosqueAttendance.mosque_id == mosque_id,
            MosqueAttendance.prayer_key == prayer_key,
            MosqueAttendance.attend_date == today,
        )
        .order_by(MosqueAttendance.created_at)
    ).all()
    return attendees, len(attendees)


@router.get("/mosques/{mosque_id}")
def mosque_detail(
    request: Request,
    mosque_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
    city: str = Depends(get_city),
):
    mosque = db.get(Mosque, mosque_id)
    if mosque is None:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"user": user, "active": "home", "title": "ค้นหามัสยิด", "message": "ไม่พบมัสยิดที่คุณค้นหา"},
            status_code=404,
        )

    prayer = get_prayer_times(city)
    next_item = next((t for t in prayer["timings"] if t["key"] == prayer["next"]), None) if prayer["ok"] else None

    attendees, attendee_count = _next_prayer_attendance(db, mosque_id, prayer["next"] if prayer["ok"] else None)
    is_attending = bool(user) and any(a.id == user.id for a in attendees)

    events = db.scalars(
        select(MosqueEvent).where(MosqueEvent.mosque_id == mosque_id).order_by(MosqueEvent.id)
    ).all()

    return templates.TemplateResponse(
        request,
        "mosque_detail.html",
        {
            "user": user,
            "active": "home",
            "mosque": mosque,
            "prayer": prayer,
            "next_item": next_item,
            "attendees": attendees[:5],
            "attendee_extra": max(0, attendee_count - 5),
            "attendee_count": attendee_count,
            "is_attending": is_attending,
            "events": events,
        },
    )


@router.post("/mosques/{mosque_id}/attend")
def toggle_attendance(
    mosque_id: int,
    city: str = Depends(get_city),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    mosque = db.get(Mosque, mosque_id)
    if mosque is None:
        return RedirectResponse("/mosques", status_code=303)

    prayer = get_prayer_times(city)
    prayer_key = prayer["next"] if prayer["ok"] else None
    if prayer_key:
        today = now_local().date()
        existing = db.scalar(
            select(MosqueAttendance).where(
                MosqueAttendance.mosque_id == mosque_id,
                MosqueAttendance.user_id == user.id,
                MosqueAttendance.prayer_key == prayer_key,
                MosqueAttendance.attend_date == today,
            )
        )
        if existing:
            db.delete(existing)
        else:
            db.add(
                MosqueAttendance(
                    mosque_id=mosque_id, user_id=user.id, prayer_key=prayer_key, attend_date=today
                )
            )
        db.commit()

    return RedirectResponse(f"/mosques/{mosque_id}", status_code=303)


@router.get("/api/mosques", response_model=list[MosqueOut])
def mosque_api(db: Session = Depends(get_db)):
    mosques = db.scalars(select(Mosque).order_by(Mosque.name)).all()
    return [
        MosqueOut(
            id=m.id, name=m.name, address=m.address, phone=m.phone, lat=m.lat, lng=m.lng
        )
        for m in mosques
    ]
