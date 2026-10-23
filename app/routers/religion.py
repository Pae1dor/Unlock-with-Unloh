"""ศาสนา — the tab with the ayah of the day, ดุอาอ์ and หลักศาสนา, plus the pages they open
(one hadith, one category) and the วิธีละหมาด guide linked from /prayer-times.

Everything religious here is read from HadeethEnc (app/services/hadeethenc.py), with its
source and grade shown; nothing is written by hand in this app.
"""
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from app.deps import get_current_user
from app.models import User
from app.services import alquran, hadeethenc
from app.templating import templates

router = APIRouter(tags=["religion"])

VIEWS = ("daily", "dua", "faith")
DEFAULT_BACK = "/religion?view=dua"


def _safe_back(value: str | None, fallback: str = DEFAULT_BACK) -> str:
    """Only same-site relative links, as the login page does for ?next=."""
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return fallback
    return value


def _error_page(request: Request, user: User | None, message: str, back: str):
    return templates.TemplateResponse(
        request,
        "error.html",
        {"user": user, "active": "religion", "title": "ศาสนา", "message": message, "back_url": back},
        status_code=404,
    )


@router.get("/daily-quran", include_in_schema=False)
def daily_quran_moved():
    # The ayah of the day is now the first view of the ศาสนา tab; old links and bookmarks land there.
    return RedirectResponse("/religion?view=daily", status_code=303)


@router.get("/religion")
def religion(request: Request, view: str = "daily", user: User | None = Depends(get_current_user)):
    if view not in VIEWS:
        view = "daily"
    context: dict = {"user": user, "active": "religion", "view": view}

    if view == "daily":
        # The ayah itself is picked and fetched in the browser (static/js/daily-quran.js) so the
        # page can show its own loading / error state; only the Thai surah names come from here.
        context.update(
            surah_names_th=alquran.SURAH_NAMES_TH,
            api_base=alquran.BASE_URL,
            editions=f"{alquran.ARABIC_EDITION},{alquran.THAI_EDITION}",
        )
    elif view == "dua":
        context.update(hadeethenc.groups(hadeethenc.DUA_CATEGORIES))
    else:
        context.update(hadeethenc.faith_overview())

    return templates.TemplateResponse(request, "religion.html", context)


@router.get("/religion/category/{category_id}")
def religion_category(request: Request, category_id: int, user: User | None = Depends(get_current_user)):
    result = hadeethenc.category(category_id)
    if not result["ok"] and result["error"] == hadeethenc.NOT_FOUND_ERROR:
        return _error_page(request, user, result["error"], "/religion?view=faith")
    return templates.TemplateResponse(
        request,
        "religion_category.html",
        {
            "user": user,
            "active": "religion",
            "category": result["category"],
            "hadiths": result["hadiths"],
            "error": result["error"],
            "back_url": "/religion?view=faith",
            "back_to": f"/religion/category/{category_id}",
        },
    )


@router.get("/hadith/{hadith_id}")
def hadith_detail(
    request: Request,
    hadith_id: int,
    back: str | None = None,
    user: User | None = Depends(get_current_user),
):
    back_url = _safe_back(back)
    if hadith_id < 1 or hadith_id > 10_000_000:
        return _error_page(request, user, hadeethenc.NOT_FOUND_ERROR, back_url)
    result = hadeethenc.hadith(hadith_id)
    if not result["ok"] and result["error"] == hadeethenc.NOT_FOUND_ERROR:
        return _error_page(request, user, result["error"], back_url)
    return templates.TemplateResponse(
        request,
        "hadith.html",
        {
            "user": user,
            "active": "religion",
            "hadith": result["hadith"],
            "error": result["error"],
            "back_url": back_url,
        },
    )


@router.get("/prayer-guide")
def prayer_guide(request: Request, user: User | None = Depends(get_current_user)):
    result = hadeethenc.groups(hadeethenc.PRAYER_CATEGORIES)
    return templates.TemplateResponse(
        request,
        "prayer_guide.html",
        {
            "user": user,
            "active": "",
            "groups": result["groups"],
            "error": result["error"],
            "back_url": "/prayer-times",
            "back_to": "/prayer-guide",
        },
    )
