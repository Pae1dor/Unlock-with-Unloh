"""Application settings, read from environment / .env file."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent

# Shown bottom-right on every page; bump on each test round.
APP_VERSION = "0.0.10"
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))

DEFAULT_CITY = os.getenv("DEFAULT_CITY", "กรุงเทพมหานคร")
COUNTRY = "Thailand"

COOKIE_NAME = "access_token"
CITY_COOKIE = "city"

# Sent to OpenStreetMap services (Overpass, Nominatim); their policies require an app identifier.
UPSTREAM_USER_AGENT = "UnlockWithUnloh/0.1 (+https://github.com/Pae1dor/Unlock-with-Unloh)"
CACHE_DIR = BASE_DIR / ".cache"

STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
QR_DIR = STATIC_DIR / "qr"
# Files users upload (report screenshots). Outside /static on purpose: they are private and
# served only through a permission-checked route. A Docker volume keeps them across rebuilds.
UPLOAD_DIR = BASE_DIR / "uploads"

TIMEZONE = "Asia/Bangkok"
