"""ข่าวสาร — category-tabbed list and detail page."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import News, User
from app.templating import NEWS_CATEGORY_LABELS, templates

router = APIRouter(tags=["news"])


@router.get("/news")
def news_list(
    request: Request,
    category: str = "all",
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    if category not in NEWS_CATEGORY_LABELS:
        category = "all"

    query = select(News).order_by(News.published_at.desc())
    if category != "all":
        query = query.where(News.category == category)
    items = db.scalars(query).all()

    return templates.TemplateResponse(
        request,
        "news_list.html",
        {"user": user, "active": "news", "items": items, "category": category},
    )


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
