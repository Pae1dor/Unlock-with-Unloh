"""Shared Jinja2 environment plus the globals/filters every template relies on."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from fastapi.templating import Jinja2Templates

from app.config import APP_VERSION, STATIC_DIR, TEMPLATES_DIR, TIMEZONE
from app.permissions import can
from app.services.aladhan import THAI_MONTHS

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

NEWS_CATEGORIES = [
    ("all", "ทั้งหมด"),
    ("article", "บทความ"),
    ("event", "กิจกรรม"),
    ("announcement", "ประกาศ"),
]
NEWS_CATEGORY_LABELS = {key: label for key, label in NEWS_CATEGORIES}

# 2D character options (spec §9): both genders from day one, plus a
# non-figurative option for those who avoid depicting living beings.
AVATAR_STYLES = [
    ("male", "ชาย"),
    ("female", "หญิง"),
    ("symbol", "สัญลักษณ์"),
]
AVATAR_STYLE_KEYS = {key for key, _ in AVATAR_STYLES}

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


def static_url(path: str) -> str:
    """/static URL with the file's modified time appended, so browsers never keep
    running a stale cached copy after the file changes."""
    try:
        stamp = int((STATIC_DIR / path).stat().st_mtime)
    except OSError:
        return f"/static/{path}"
    return f"/static/{path}?v={stamp}"


# App themes, picked on /profile: key -> the browser's address-bar colour. "green" (ขาว-เขียว)
# is the default; the rest of a theme lives in static/css/style.css under html[data-theme].
THEME_COLORS = {"green": "#1B5E3A", "gold": "#9c762b", "dark": "#143b28"}
THEME_COOKIE = "theme"


def theme_of(request) -> str:
    """The visitor's theme from its cookie; anything unknown is the default."""
    value = request.cookies.get(THEME_COOKIE)
    return value if value in THEME_COLORS else "green"


def theme_color_of(request) -> str:
    return THEME_COLORS[theme_of(request)]


templates.env.filters["thai_datetime"] = thai_datetime
templates.env.filters["thai_day"] = thai_day
templates.env.filters["baht"] = baht
templates.env.globals["news_categories"] = NEWS_CATEGORIES
templates.env.globals["news_category_labels"] = NEWS_CATEGORY_LABELS
templates.env.globals["forum_categories"] = FORUM_CATEGORIES
templates.env.globals["forum_category_labels"] = FORUM_CATEGORY_LABELS
templates.env.globals["avatar_styles"] = AVATAR_STYLES
templates.env.globals["app_version"] = APP_VERSION
templates.env.globals["static_url"] = static_url
templates.env.globals["theme_of"] = theme_of
templates.env.globals["theme_color_of"] = theme_color_of
templates.env.globals["app_name"] = "ประชาชนเพื่อพี่น้องอิสลาม"
# can(user, "news.manage") — permission checks in templates (app/permissions.py)
templates.env.globals["can"] = can
