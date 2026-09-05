"""Shared Jinja2 environment plus the globals/filters every template relies on."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi.templating import Jinja2Templates

from app.config import TEMPLATES_DIR, TIMEZONE
from app.services.aladhan import THAI_MONTHS

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

NEWS_CATEGORIES = [
    ("all", "ทั้งหมด"),
    ("article", "บทความ"),
    ("event", "กิจกรรม"),
    ("announcement", "ประกาศ"),
]
NEWS_CATEGORY_LABELS = {key: label for key, label in NEWS_CATEGORIES}

FORUM_CATEGORIES = [
    ("qa", "ถาม-ตอบ"),
    ("article", "บทความ"),
    ("announce", "ประกาศ"),
]
FORUM_CATEGORY_LABELS = {key: label for key, label in FORUM_CATEGORIES}


def _as_local(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(ZoneInfo(TIMEZONE))


def thai_datetime(value: datetime | None) -> str:
    """e.g. '5 ก.ย. 2569 14:03'."""
    if value is None:
        return ""
    local = _as_local(value)
    return f"{local.day} {THAI_MONTHS[local.month - 1]} {local.year + 543} {local:%H:%M}"


def thai_day(value: datetime | None) -> str:
    """e.g. '5 กันยายน 2569'."""
    if value is None:
        return ""
    local = _as_local(value)
    return f"{local.day} {THAI_MONTHS[local.month - 1]} {local.year + 543}"


def baht(value) -> str:
    try:
        return f"{float(value):,.2f}"
    except (TypeError, ValueError):
        return "0.00"


templates.env.filters["thai_datetime"] = thai_datetime
templates.env.filters["thai_day"] = thai_day
templates.env.filters["baht"] = baht
templates.env.globals["news_categories"] = NEWS_CATEGORIES
templates.env.globals["news_category_labels"] = NEWS_CATEGORY_LABELS
templates.env.globals["forum_categories"] = FORUM_CATEGORIES
templates.env.globals["forum_category_labels"] = FORUM_CATEGORY_LABELS
templates.env.globals["app_name"] = "ประชาชนเพื่อพี่น้องอิสลาม"
