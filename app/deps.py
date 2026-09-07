"""Shared FastAPI dependencies: current user from the httpOnly cookie, active city."""
from urllib.parse import unquote

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.auth import decode_access_token
from app.config import CITY_COOKIE, COOKIE_NAME, DEFAULT_CITY
from app.database import get_db
from app.models import User


class LoginRequired(Exception):
    """Raised by require_user; converted into a redirect to /login by an exception handler."""

    def __init__(self, next_url: str = "/"):
        self.next_url = next_url


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User | None:
    """Return the logged-in User, or None for anonymous visitors."""
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    user_id = decode_access_token(token)
    if user_id is None:
        return None
    return db.get(User, user_id)


def require_user(request: Request, user: User | None = Depends(get_current_user)) -> User:
    """Same as get_current_user but bounces anonymous visitors to /login."""
    if user is None:
        raise LoginRequired(next_url=str(request.url.path))
    return user


def get_city(request: Request, user: User | None = Depends(get_current_user)) -> str:
    """City used for prayer times / qibla lookups: cookie wins, then profile, then default."""
    cookie_city = request.cookies.get(CITY_COOKIE)
    if cookie_city:
        # Cookie values must be Latin-1 (HTTP header rules), so Thai city
        # names are percent-encoded on write (see /set-city) and decoded here.
        return unquote(cookie_city)
    if user is not None and user.city:
        return user.city
    return DEFAULT_CITY


def redirect_to_login(next_url: str = "/") -> RedirectResponse:
    return RedirectResponse(url=f"/login?next={next_url}", status_code=303)
