"""อุมมะฮ์ — ชุมชน and ข่าวสาร on one page, switched by the toggle in the top bar."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import User
from app.routers.community import list_posts
from app.routers.news import list_news
from app.templating import NEWS_CATEGORY_LABELS, templates

router = APIRouter(tags=["ummah"])


@router.get("/ummah")
def ummah(
    request: Request,
    view: str = "community",
    tab: str = "popular",
    category: str = "all",
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    if view not in ("community", "news"):
        view = "community"
    if tab not in ("popular", "latest"):
        tab = "popular"
    if category not in NEWS_CATEGORY_LABELS:
        category = "all"

    # Both views are rendered so the toggle swaps them without reloading the page.
    return templates.TemplateResponse(
        request,
        "ummah.html",
        {
            "user": user,
            "active": "ummah",
            "view": view,
            "posts": list_posts(db, tab),
            "tab": tab,
            "items": list_news(db, category),
            "category": category,
        },
    )
