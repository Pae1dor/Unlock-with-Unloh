"""ข่าวสาร — category-tabbed list, detail page, and admin-only create."""
import time

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import News, User
from app.permissions import require
from app.templating import NEWS_CATEGORY_LABELS, templates

router = APIRouter(tags=["news"])

# Rotated across newly-created posts so the thumbnail strip doesn't look monotone.
THUMB_COLORS = ["#1B5E3A", "#2E7D52", "#8B6B2E", "#1F6B3A", "#2A5F8F", "#6B4C9A", "#9A3B3B"]


def list_news(db: Session, category: str) -> list[News]:
    """News items for the ข่าวสาร view of /ummah; category "all" means no filter."""
    query = select(News).order_by(News.published_at.desc())
    if category != "all":
        query = query.where(News.category == category)
    return db.scalars(query).all()


@router.get("/news")
def news_list(category: str = "all"):
    # The list now lives on /ummah (ชุมชน | ข่าวสาร); old links land on the ข่าวสาร view.
    if category not in NEWS_CATEGORY_LABELS:
        category = "all"
    return RedirectResponse(f"/ummah?view=news&category={category}", status_code=303)


@router.get("/news/new")
def new_news_form(request: Request, user: User = Depends(require("news.manage"))):
    return templates.TemplateResponse(
        request,
        "news_new.html",
        {"user": user, "active": "news", "error": None, "form": {}},
    )


@router.post("/news/new")
def create_news(
    request: Request,
    title: str = Form(...),
    category: str = Form("article"),
    summary: str = Form(""),
    content: str = Form(...),
    user: User = Depends(require("news.manage")),
    db: Session = Depends(get_db),
):
    form = {
        "title": title.strip(),
        "category": category,
        "summary": summary.strip(),
        "content": content.strip(),
    }
    if category not in NEWS_CATEGORY_LABELS or category == "all":
        form["category"] = "article"

    if not form["title"] or not form["content"]:
        return templates.TemplateResponse(
            request,
            "news_new.html",
            {"user": user, "active": "news", "error": "กรุณากรอกหัวข้อและเนื้อหาข่าว", "form": form},
            status_code=400,
        )

    post_count = db.scalar(select(func.count(News.id))) or 0
    color = THUMB_COLORS[post_count % len(THUMB_COLORS)]

    item = News(
        title=form["title"],
        slug=f"news-{int(time.time())}",
        category=form["category"],
        summary=form["summary"],
        content=form["content"],
        image_color=color,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return RedirectResponse(f"/news/{item.id}", status_code=303)


@router.get("/news/{news_id}")
def news_detail(
    request: Request,
    news_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    item = db.get(News, news_id)
    if item is None:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"user": user, "active": "news", "title": "ข่าวสาร", "message": "ไม่พบข่าวที่คุณค้นหา"},
            status_code=404,
        )
    return templates.TemplateResponse(
        request, "news_detail.html", {"user": user, "active": "news", "item": item}
    )
