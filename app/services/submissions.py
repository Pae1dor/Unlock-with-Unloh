"""What users send to the admins — mosque requests (เพิ่มมัสยิด) and reports (แจ้งปัญหา).

Spam guard: login required, and at most DAILY_LIMIT submissions per user per local day,
both kinds counted together.

Report images are re-encoded with Pillow before saving: that checks they really are images,
caps their size, and drops EXIF metadata (phone photos carry the GPS position they were
taken at). They live in UPLOAD_DIR/reports, outside /static, and are served only to the
sender and to admins (routers/reports.py).
"""
from __future__ import annotations

import io
import secrets
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

from PIL import Image, ImageOps, UnidentifiedImageError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import TIMEZONE, UPLOAD_DIR
from app.models import AppMosque, MosqueRequest, Report, User
from app.services import mosque_index

DAILY_LIMIT = 5

REPORT_CATEGORIES = [
    ("bug", "บั๊กแอป"),
    ("mosque_info", "ข้อมูลมัสยิดผิด"),
    ("content", "เนื้อหาไม่เหมาะสม"),
    ("idea", "เสนอไอเดีย"),
]
REPORT_CATEGORY_LABELS = dict(REPORT_CATEGORIES)

REQUEST_STATUS_LABELS = {"pending": "รอตรวจ", "approved": "อนุมัติแล้ว", "rejected": "ไม่อนุมัติ"}
REPORT_STATUS_LABELS = {"open": "รอตรวจ", "resolved": "แก้ไขแล้ว", "dismissed": "ปิดเรื่องแล้ว"}

# Requests must be pinned inside Thailand (the app's mosque data covers Thailand only).
THAILAND_BOUNDS = (5.4, 20.6, 97.2, 105.8)   # lat min, lat max, lng min, lng max

REPORT_IMAGE_DIR = UPLOAD_DIR / "reports"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024    # checked on the raw bytes, before Pillow opens them
MAX_IMAGE_SIDE = 1600
# Decompression-bomb guard: a 48 MP phone photo is ~48M px. Pillow itself raises above 2x
# this limit; the explicit check in save_report_image refuses anything above 1x.
MAX_IMAGE_PIXELS = 50_000_000
Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


class SubmitError(Exception):
    """A refused submission; `message` is shown to the user as is."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class ReviewError(Exception):
    pass


# ---------- spam guard ----------

def _local_midnight_utc() -> datetime:
    tz = ZoneInfo(TIMEZONE)
    today = datetime.now(tz).date()
    return datetime.combine(today, time.min, tzinfo=tz).astimezone(timezone.utc)


def submitted_today(db: Session, user_id: int) -> int:
    since = _local_midnight_utc()
    requests = db.scalar(select(func.count(MosqueRequest.id)).where(
        MosqueRequest.user_id == user_id, MosqueRequest.created_at >= since)) or 0
    reports = db.scalar(select(func.count(Report.id)).where(
        Report.user_id == user_id, Report.created_at >= since)) or 0
    return requests + reports


def check_daily_limit(db: Session, user: User) -> None:
    if submitted_today(db, user.id) >= DAILY_LIMIT:
        raise SubmitError(f"วันนี้ส่งครบ {DAILY_LIMIT} เรื่องแล้ว ส่งเพิ่มได้อีกครั้งพรุ่งนี้")


# ---------- mosque requests ----------

def in_thailand(lat: float, lng: float) -> bool:
    lat_min, lat_max, lng_min, lng_max = THAILAND_BOUNDS
    return lat_min <= lat <= lat_max and lng_min <= lng <= lng_max


def nearest_osm_mosque(lat: float, lng: float, within_m: float = 50.0) -> dict | None:
    """For the admin: an OSM mosque already at (almost) the same spot, if any."""
    if not mosque_index.available():
        return None
    best, best_d = None, within_m
    box = 0.001   # ~110 m; exact distance below
    for m in mosque_index.in_bbox(lat - box, lng - box, lat + box, lng + box):
        d = mosque_index.haversine_m(lat, lng, m["lat"], m["lng"])
        if d <= best_d:
            best, best_d = m, d
    return {"name": best["name"], "distance_m": round(best_d)} if best else None


def approve_request(db: Session, request_id: int, admin: User) -> AppMosque:
    req = db.scalar(select(MosqueRequest).where(MosqueRequest.id == request_id).with_for_update())
    if req is None or req.status != "pending":
        db.rollback()
        raise ReviewError("not_pending")
    mosque = AppMosque(
        name=req.name, lat=req.lat, lng=req.lng, address=req.address,
        opening_hours=req.opening_hours, has_women_area=req.has_women_area,
        has_jumuah=req.has_jumuah, approved_by=admin.id,
    )
    db.add(mosque)
    db.flush()
    req.status = "approved"
    req.app_mosque_id = mosque.id
    req.reviewed_by = admin.id
    req.reviewed_at = datetime.now(timezone.utc)
    db.commit()
    return mosque


def reject_request(db: Session, request_id: int, admin: User, note: str) -> None:
    req = db.scalar(select(MosqueRequest).where(MosqueRequest.id == request_id).with_for_update())
    if req is None or req.status != "pending":
        db.rollback()
        raise ReviewError("not_pending")
    req.status = "rejected"
    req.review_note = note.strip()[:400]
    req.reviewed_by = admin.id
    req.reviewed_at = datetime.now(timezone.utc)
    db.commit()


# ---------- reports ----------

def save_report_image(data: bytes) -> str:
    """Validate and re-encode an uploaded image; returns the stored file name."""
    if len(data) > MAX_UPLOAD_BYTES:
        raise SubmitError("รูปใหญ่เกินไป (ไม่เกิน 5 MB)")
    try:
        with Image.open(io.BytesIO(data)) as probe:
            if probe.format not in ("JPEG", "PNG", "WEBP", "GIF", "HEIF", "MPO"):
                raise SubmitError("รองรับเฉพาะรูป JPG, PNG หรือ WEBP")
            if probe.width * probe.height > MAX_IMAGE_PIXELS:
                raise SubmitError("รูปมีขนาดใหญ่เกินไป")
            img = ImageOps.exif_transpose(probe)   # keep phone photos upright once EXIF is gone
            img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
            if img.mode not in ("RGB", "L"):
                background = Image.new("RGB", img.size, (255, 255, 255))
                rgba = img.convert("RGBA")
                background.paste(rgba, mask=rgba.split()[-1])
                img = background
            out = io.BytesIO()
            img.convert("RGB").save(out, "JPEG", quality=85, optimize=True)   # no EXIF written
    except SubmitError:
        raise
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise SubmitError("ไฟล์นี้ไม่ใช่รูปภาพ หรือไฟล์เสีย") from None

    REPORT_IMAGE_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{secrets.token_hex(16)}.jpg"
    (REPORT_IMAGE_DIR / name).write_bytes(out.getvalue())
    return name


def close_report(db: Session, report_id: int, admin: User, status: str) -> None:
    if status not in ("resolved", "dismissed"):
        raise ReviewError("bad_status")
    report = db.scalar(select(Report).where(Report.id == report_id).with_for_update())
    if report is None or report.status != "open":
        db.rollback()
        raise ReviewError("not_open")
    report.status = status
    report.reviewed_by = admin.id
    report.reviewed_at = datetime.now(timezone.utc)
    db.commit()
