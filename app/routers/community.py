"""ชุมชน — forum list, create post, detail, AJAX like and comments."""
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_user
from app.models import ForumComment, ForumLike, ForumPost, User
from app.schemas import CommentIn, CommentOut, LikeOut
from app.templating import FORUM_CATEGORY_LABELS, templates, thai_datetime

router = APIRouter(tags=["community"])


@router.get("/community")
def community(
    request: Request,
    tab: str = "popular",
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    if tab not in ("popular", "latest"):
        tab = "popular"

    if tab == "popular":
        # Most-liked first; ties broken by recency.
        like_count = (
            select(ForumLike.post_id, func.count(ForumLike.id).label("n"))
            .group_by(ForumLike.post_id)
            .subquery()
        )
        query = (
            select(ForumPost)
            .outerjoin(like_count, like_count.c.post_id == ForumPost.id)
            .order_by(func.coalesce(like_count.c.n, 0).desc(), ForumPost.created_at.desc())
        )
    else:
        query = select(ForumPost).order_by(ForumPost.created_at.desc())

    posts = db.scalars(query).all()
    return templates.TemplateResponse(
        request,
        "community.html",
        {"user": user, "active": "community", "posts": posts, "tab": tab},
    )


@router.get("/community/new")
def new_post_form(request: Request, user: User = Depends(require_user)):
    return templates.TemplateResponse(
        request,
        "community_new.html",
        {"user": user, "active": "community", "error": None, "form": {}},
    )


@router.post("/community/new")
def create_post(
    request: Request,
    title: str = Form(...),
    category: str = Form("qa"),
    content: str = Form(...),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    form = {"title": title.strip(), "category": category, "content": content.strip()}
    if not form["title"] or not form["content"]:
        return templates.TemplateResponse(
            request,
            "community_new.html",
            {
                "user": user,
                "active": "community",
                "error": "กรุณากรอกหัวข้อและเนื้อหาให้ครบถ้วน",
                "form": form,
            },
            status_code=400,
        )
    if form["category"] not in FORUM_CATEGORY_LABELS:
        form["category"] = "qa"

    post = ForumPost(
        user_id=user.id,
        title=form["title"],
        category=form["category"],
        content=form["content"],
    )
    db.add(post)
    db.commit()
    db.refresh(post)
    return RedirectResponse(f"/community/{post.id}", status_code=303)


@router.get("/community/{post_id}")
def post_detail(
    request: Request,
    post_id: int,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    post = db.get(ForumPost, post_id)
    if post is None:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"user": user, "active": "community", "title": "ชุมชน", "message": "ไม่พบกระทู้ที่คุณค้นหา"},
            status_code=404,
        )

    liked = False
    if user is not None:
        liked = (
            db.scalar(
                select(ForumLike).where(
                    ForumLike.post_id == post.id, ForumLike.user_id == user.id
                )
            )
            is not None
        )

    return templates.TemplateResponse(
        request,
        "community_detail.html",
        {"user": user, "active": "community", "post": post, "liked": liked},
    )


@router.post("/api/community/{post_id}/like", response_model=LikeOut)
def toggle_like(
    post_id: int,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    post = db.get(ForumPost, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="ไม่พบกระทู้")

    existing = db.scalar(
        select(ForumLike).where(ForumLike.post_id == post_id, ForumLike.user_id == user.id)
    )
    if existing is None:
        db.add(ForumLike(post_id=post_id, user_id=user.id))
        liked = True
    else:
        db.delete(existing)
        liked = False
    db.commit()

    count = db.scalar(select(func.count(ForumLike.id)).where(ForumLike.post_id == post_id)) or 0
    return LikeOut(liked=liked, like_count=count)


@router.post("/api/community/{post_id}/comments", response_model=CommentOut)
def add_comment(
    post_id: int,
    payload: CommentIn,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    post = db.get(ForumPost, post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="ไม่พบกระทู้")

    content = payload.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="กรุณากรอกความคิดเห็น")

    comment = ForumComment(post_id=post_id, user_id=user.id, content=content)
    db.add(comment)
    db.commit()
    db.refresh(comment)

    return CommentOut(
        id=comment.id,
        author_name=user.full_name,
        author_initial=user.initial,
        content=comment.content,
        created_at=thai_datetime(comment.created_at),
    )
