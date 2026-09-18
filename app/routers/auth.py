"""Registration, login and logout. JWT is stored in an httpOnly `access_token` cookie."""
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth import create_access_token, hash_password, verify_password
from app.config import ACCESS_TOKEN_EXPIRE_MINUTES, COOKIE_NAME
from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.templating import AVATAR_STYLE_KEYS, templates

router = APIRouter(tags=["auth"])


def _safe_next(value: str | None) -> str:
    """Only allow same-site relative redirects."""
    if not value or not value.startswith("/") or value.startswith("//"):
        return "/"
    return value


def _set_cookie(response: RedirectResponse, user_id: int) -> RedirectResponse:
    response.set_cookie(
        key=COOKIE_NAME,
        value=create_access_token(user_id),
        httponly=True,
        samesite="lax",
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
    )
    return response


@router.get("/register")
def register_form(request: Request, user: User | None = Depends(get_current_user)):
    if user is not None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request, "register.html", {"user": None, "active": "profile", "error": None, "form": {}}
    )


@router.post("/register")
def register_submit(
    request: Request,
    full_name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirm_password: str = Form(...),
    avatar_style: str = Form("male"),
    db: Session = Depends(get_db),
):
    if avatar_style not in AVATAR_STYLE_KEYS:
        avatar_style = "male"
    form = {
        "full_name": full_name.strip(),
        "email": email.strip().lower(),
        "avatar_style": avatar_style,
    }

    def fail(message: str):
        return templates.TemplateResponse(
            request,
            "register.html",
            {"user": None, "active": "profile", "error": message, "form": form},
            status_code=400,
        )

    if not form["full_name"]:
        return fail("กรุณากรอกชื่อ-นามสกุล")
    if "@" not in form["email"]:
        return fail("รูปแบบอีเมลไม่ถูกต้อง")
    if len(password) < 6:
        return fail("รหัสผ่านต้องมีอย่างน้อย 6 ตัวอักษร")
    if password != confirm_password:
        return fail("รหัสผ่านทั้งสองช่องไม่ตรงกัน")

    existing = db.scalar(select(User).where(User.email == form["email"]))
    if existing is not None:
        return fail("อีเมลนี้ถูกใช้งานแล้ว")

    user = User(
        full_name=form["full_name"],
        email=form["email"],
        hashed_password=hash_password(password),
        avatar_style=form["avatar_style"],
    )
    db.add(user)
    db.commit()
    return RedirectResponse("/login?registered=1", status_code=303)


@router.get("/login")
def login_form(request: Request, user: User | None = Depends(get_current_user)):
    if user is not None:
        return RedirectResponse("/", status_code=303)
    return templates.TemplateResponse(
        request,
        "login.html",
        {
            "user": None,
            "active": "profile",
            "error": None,
            "registered": request.query_params.get("registered") == "1",
            "next": _safe_next(request.query_params.get("next")),
            "form": {},
        },
    )


@router.post("/login")
def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    next: str = Form("/"),
    db: Session = Depends(get_db),
):
    email = email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {
                "user": None,
                "active": "profile",
                "error": "อีเมลหรือรหัสผ่านไม่ถูกต้อง",
                "registered": False,
                "next": _safe_next(next),
                "form": {"email": email},
            },
            status_code=401,
        )

    response = RedirectResponse(_safe_next(next), status_code=303)
    return _set_cookie(response, user.id)


@router.get("/logout")
def logout():
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response
