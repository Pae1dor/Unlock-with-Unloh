"""อัลกุรอาน — surah list and per-surah reader."""
from fastapi import APIRouter, Depends, Request

from app.deps import get_current_user
from app.models import User
from app.services import alquran
from app.templating import templates

router = APIRouter(tags=["quran"])


@router.get("/quran")
def surah_list(request: Request, user: User | None = Depends(get_current_user)):
    result = alquran.get_surah_list()
    return templates.TemplateResponse(
        request,
        "quran_list.html",
        {
            "user": user,
            "active": "home",
            "surahs": result["surahs"],
            "error": result["error"],
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
