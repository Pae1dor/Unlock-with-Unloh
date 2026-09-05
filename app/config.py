"""Application settings, read from environment / .env file."""
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dev.db")
SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080"))

DEFAULT_CITY = os.getenv("DEFAULT_CITY", "กรุงเทพมหานคร")
COUNTRY = "Thailand"

COOKIE_NAME = "access_token"
CITY_COOKIE = "city"

STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "templates"
QR_DIR = STATIC_DIR / "qr"

TIMEZONE = "Asia/Bangkok"
