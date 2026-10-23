"""อัลกุรอาน — surah / juz lists, per-surah and per-juz readers and the ayah of the day."""
from fastapi import APIRouter, Depends, Request

from app.deps import get_current_user
from app.models import User
from app.services import alquran
from app.templating import templates

router = APIRouter(tags=["quran"])


@router.get("/daily-quran")
def daily_quran(request: Request, user: User | None = Depends(get_current_user)):
    # The ayah itself is picked and fetched in the browser (static/js/daily-quran.js) so the
    # page can show its own loading / error state; only the Thai surah names come from here.
    return templates.TemplateResponse(
        request,
        "daily_quran.html",
        {
            "user": user,
            "active": "daily_quran",
            "surah_names_th": alquran.SURAH_NAMES_TH,
            "api_base": alquran.BASE_URL,
            "editions": f"{alquran.ARABIC_EDITION},{alquran.THAI_EDITION}",
        },
    )


@router.get("/quran")
def surah_list(request: Request, view: str = "surah", user: User | None = Depends(get_current_user)):
    # ?view=juz lists the 30 juz instead of the 114 surahs; plain links, so back/refresh work.
    if view == "juz":
        return templates.TemplateResponse(
            request,
            "quran_list.html",
            {"user": user, "active": "home", "view": "juz", "juz_list": alquran.juz_list(), "surahs": [], "error": None},
        )
    result = alquran.get_surah_list()
    return templates.TemplateResponse(
        request,
        "quran_list.html",
        {
            "user": user,
            "active": "home",
            "view": "surah",
            "juz_list": [],
            "surahs": result["surahs"],
            "error": result["error"],
        },
    )


@router.get("/quran/juz/{juz_number}")
def juz_detail(request: Request, juz_number: int, user: User | None = Depends(get_current_user)):
    if juz_number < 1 or juz_number > alquran.JUZ_COUNT:
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "user": user,
                "active": "home",
                "title": "อัลกุรอาน",
                "message": f"หมายเลขญุซต้องอยู่ระหว่าง 1 ถึง {alquran.JUZ_COUNT}",
            },
            status_code=404,
        )

    result = alquran.get_juz(juz_number)
    return templates.TemplateResponse(
        request,
        "quran_juz.html",
        {
            "user": user,
            "active": "home",
            "juz": result["juz"],
            "sections": result["sections"],
            "error": result["error"],
            "juz_number": juz_number,
            "juz_count": alquran.JUZ_COUNT,
        },
    )


@router.get("/quran/{surah_number}")
def surah_detail(request: Request, surah_number: int, user: User | None = Depends(get_current_user)):
    if surah_number < 1 or surah_number > 114:
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "user": user,
                "active": "home",
                "title": "อัลกุรอาน",
                "message": "หมายเลขซูเราะฮ์ต้องอยู่ระหว่าง 1 ถึง 114",
            },
            status_code=404,
        )

    result = alquran.get_surah(surah_number)
    return templates.TemplateResponse(
        request,
        "quran_detail.html",
        {
            "user": user,
            "active": "home",
            "surah": result["surah"],
            "ayahs": result["ayahs"],
            "error": result["error"],
            "fallback_name": alquran.thai_name(surah_number),
            "surah_number": surah_number,
        },
    )
