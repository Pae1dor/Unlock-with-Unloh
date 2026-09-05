"""FastAPI application entry point."""
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import QR_DIR, STATIC_DIR
from app.database import init_db
from app.deps import LoginRequired
from app.routers import (
    auth as auth_router,
    community,
    donation,
    home,
    mosques,
    news,
    prayer,
    profile,
    quran,
)
from app.templating import templates


@asynccontextmanager
async def lifespan(app: FastAPI):
    QR_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    yield


app = FastAPI(title="ประชาชนเพื่อพี่น้องอิสลาม", lifespan=lifespan)

STATIC_DIR.mkdir(parents=True, exist_ok=True)
QR_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.exception_handler(LoginRequired)
async def login_required_handler(request: Request, exc: LoginRequired):
    return RedirectResponse(url=f"/login?next={exc.next_url}", status_code=303)


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "title": "ไม่พบหน้านี้",
            "message": "ไม่พบหน้าที่คุณกำลังค้นหา",
            "user": None,
            "active": "",
        },
        status_code=404,
    )


app.include_router(auth_router.router)
app.include_router(home.router)
app.include_router(prayer.router)
app.include_router(quran.router)
app.include_router(donation.router)
app.include_router(mosques.router)
app.include_router(news.router)
app.include_router(community.router)
app.include_router(profile.router)
