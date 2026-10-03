"""FastAPI application entry point."""
import mimetypes
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app import access_log
from app.config import QR_DIR, STATIC_DIR
from app.database import init_db
from app.deps import LoginRequired
from app.routers import (
    auth as auth_router,
    checkins,
    community,
    donation,
    home,
    mosques,
    news,
    prayer,
    profile,
    quran,
)
from app.services import mosque_index
from app.templating import templates

access_log.install()


@asynccontextmanager
async def lifespan(app: FastAPI):
    QR_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    # Nationwide mosque list for the finder: loads the saved file, downloads it in the
    # background when missing or older than a day.
    mosque_index.start()
    yield
    mosque_index.stop()


app = FastAPI(title="ประชาชนเพื่อพี่น้องอิสลาม", lifespan=lifespan)

STATIC_DIR.mkdir(parents=True, exist_ok=True)
QR_DIR.mkdir(parents=True, exist_ok=True)
# Windows' registry has no type for .webmanifest, so StaticFiles would send text/plain.
mimetypes.add_type("application/manifest+json", ".webmanifest")
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/sw.js", include_in_schema=False)
async def service_worker():
    # Served from the site root (not /static/) so the worker's scope covers every page.
    return FileResponse(
        STATIC_DIR / "sw.js",
        media_type="text/javascript",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/.well-known/assetlinks.json", include_in_schema=False)
async def asset_links():
    assetlinks_file = STATIC_DIR / "assetlinks.json"
    if assetlinks_file.exists():
        return FileResponse(
            assetlinks_file,
            media_type="application/json",
            headers={"Cache-Control": "public, max-age=3600"},
        )
    return JSONResponse(content=[], status_code=404)




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
app.include_router(checkins.router)
app.include_router(news.router)
app.include_router(community.router)
app.include_router(profile.router)
