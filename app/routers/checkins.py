"""Check-in at an OpenStreetMap mosque ("เช็คอิน"), verified by distance on the server.

The mosque's position always comes from our nationwide file (mosque_index), never from
the client. The visitor's lat/lng/accuracy are used for the distance check only and are
neither stored nor logged. Rules (window, one per prayer per day) are in services/checkin.py.

The API speaks finder ids ("node/123" for OSM, "app:42" for mosques added through the app);
the database stores the prefixed form ("osm:node/123", "app:42"; app/mosque_ids.py). Hidden
app mosques can't be checked in to, but existing check-ins keep their stored name.
"""
import logging
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import mosque_ids
from app.database import get_db
from app.deps import get_current_user
from app.models import MosqueCheckin, User
from app.schemas import CheckinIn
from app.services import checkin as rules
from app.services import app_mosques, mosque_index
from app.services import prayer_log

router = APIRouter(tags=["checkins"])
log = logging.getLogger("uvicorn.error")

MAX_STATUS_IDS = 100


def _fail(status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status_code=status, detail={"code": code, "message": message, **extra})


def _logged_in(user: User | None) -> User:
    if user is None:
        raise _fail(401, "login", "เข้าสู่ระบบเพื่อเช็คอิน")
    return user


def _index_ready() -> None:
    if not mosque_index.available():
        raise _fail(503, "not_ready", "ระบบข้อมูลมัสยิดยังไม่พร้อม ลองใหม่อีกครั้ง")


def _format_distance(m: float) -> str:
    return f"{round(m)} ม." if m < 999.5 else f"{m / 1000:.1f} กม."


def _closed_message(upcoming: rules.Window) -> str:
    return f"เปิดเช็คอิน {upcoming.label} เวลา {upcoming.opens:%H:%M}"


def _user_checkins(db: Session, user_id: int, dates) -> dict[tuple[str, object], MosqueCheckin]:
    rows = db.scalars(
        select(MosqueCheckin).where(MosqueCheckin.user_id == user_id, MosqueCheckin.prayer_date.in_(list(dates)))
    ).all()
    return {(r.prayer_key, r.prayer_date): r for r in rows}


@router.get("/api/checkins/status")
def checkin_status(
    osm_ids: str = Query(..., max_length=4000, description="comma-separated OSM ids"),
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Per mosque: can the visitor check in right now, or when does it open, or have they already."""
    user = _logged_in(user)
    ids = [i for i in dict.fromkeys(s.strip() for s in osm_ids.split(",")) if i][:MAX_STATUS_IDS]
    if not any(mosque_ids.to_app(i) is not None for i in ids):
        _index_ready()   # app mosques don't need the OSM file
    now = rules.now_local()
    mine = _user_checkins(db, user.id, {now.date(), now.date() - timedelta(days=1)})

    out = {}
    for osm_id in ids:
        mosque = app_mosques.find(db, osm_id)
        if mosque is None:
            continue
        current, upcoming = rules.status_at(mosque["lat"], mosque["lng"], now)
        if current is None:
            out[osm_id] = {"state": "closed", "label": upcoming.label, "opens_at": f"{upcoming.opens:%H:%M}",
                           "message": _closed_message(upcoming)}
            continue
        done = mine.get((current.prayer_key, current.prayer_date))
        if done is None:
            out[osm_id] = {"state": "open", "prayer_key": current.prayer_key, "label": current.label}
        elif done.osm_id == mosque_ids.from_api(osm_id):
            out[osm_id] = {"state": "done", "prayer_key": current.prayer_key, "label": current.label,
                           "message": f"เช็คอินแล้ว ✓ ({current.label})"}
        else:
            out[osm_id] = {"state": "done_elsewhere", "prayer_key": current.prayer_key, "label": current.label,
                           "at_name": done.mosque_name, "message": f"เช็คอินเวลานี้แล้วที่ {done.mosque_name}"}
    return {"mosques": out}


@router.post("/api/checkins", status_code=201)
def create_checkin(
    body: CheckinIn,
    user: User | None = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    user = _logged_in(user)
    if mosque_ids.to_app(body.osm_id) is None:
        _index_ready()
    mosque = app_mosques.find(db, body.osm_id)
    if mosque is None:
        raise _fail(404, "unknown_mosque", "ไม่พบมัสยิดนี้")

    if body.accuracy > rules.MAX_ACCURACY_M:
        raise _fail(422, "gps_inaccurate", "สัญญาณ GPS ไม่ชัด ลองขยับไปที่โล่งหรือใกล้ประตู")

    distance = mosque_index.haversine_m(body.lat, body.lng, mosque["lat"], mosque["lng"])
    if distance > rules.CHECK_IN_RADIUS_M:
        raise _fail(422, "too_far",
                    f"อยู่ห่าง {_format_distance(distance)} ต้องไม่เกิน {int(rules.CHECK_IN_RADIUS_M)} ม.",
                    distance_m=round(distance))

    now = rules.now_local()
    current, upcoming = rules.status_at(mosque["lat"], mosque["lng"], now)
    if current is None:
        raise _fail(409, "closed", _closed_message(upcoming), opens_at=f"{upcoming.opens:%H:%M}")

    def already(existing: MosqueCheckin) -> HTTPException:
        if existing.osm_id == mosque_ids.from_api(body.osm_id):
            return _fail(409, "done", f"เช็คอินแล้ว ✓ ({current.label})")
        return _fail(409, "done_elsewhere", f"เช็คอินเวลานี้แล้วที่ {existing.mosque_name}",
                     at_name=existing.mosque_name)

    key = (current.prayer_key, current.prayer_date)
    existing = _user_checkins(db, user.id, {current.prayer_date}).get(key)
    if existing:
        raise already(existing)

    row = MosqueCheckin(
        user_id=user.id,
        osm_id=mosque_ids.from_api(body.osm_id),
        mosque_name=mosque["name"],
        prayer_key=current.prayer_key,
        prayer_date=current.prayer_date,
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        # two check-ins raced (e.g. double tap on two mosques); the other one won
        db.rollback()
        existing = _user_checkins(db, user.id, {current.prayer_date}).get(key)
        if existing:
            raise already(existing) from None
        raise

    # The check-in also marks that prayer in the user's prayer log (in congregation).
    # The check-in itself is already saved, so a failure here must not undo it.
    try:
        prayer_log.record_checkin(db, user, row, now)
    except Exception:
        db.rollback()
        log.exception("prayer log update after check-in failed")

    return {
        "state": "done",
        "osm_id": body.osm_id,
        "mosque_name": row.mosque_name,
        "prayer_key": row.prayer_key,
        "label": current.label,
        "prayer_date": row.prayer_date.isoformat(),
        "message": f"เช็คอินแล้ว ✓ ({current.label})",
    }
