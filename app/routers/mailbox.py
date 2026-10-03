"""กล่องจดหมาย — the logged-in user's own messages and gifts."""
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import require_user
from app.models import User
from app.outfits import BACKGROUNDS, OUTFITS, RARITY_LABELS
from app.services import mailbox
from app.templating import templates

router = APIRouter(tags=["mailbox"])


@router.get("/mail")
def mail_list(request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    return templates.TemplateResponse(request, "mail_list.html", {
        "user": user, "active": "profile", "mails": mailbox.inbox(db, user),
    })


@router.get("/mail/{mail_id}")
def mail_detail(mail_id: int, request: Request, user: User = Depends(require_user), db: Session = Depends(get_db)):
    mail = mailbox.get_own(db, user, mail_id)
    if mail is None:
        raise HTTPException(status_code=404)
    mailbox.mark_read(db, mail)
    gift = OUTFITS.get(mail.gift_outfit_key) if mail.gift_outfit_key else None
    gift_bg = BACKGROUNDS.get(mail.gift_background_key) if mail.gift_background_key else None
    return templates.TemplateResponse(request, "mail_detail.html", {
        "user": user, "active": "profile", "back_url": "/mail", "mail": mail, "gift": gift, "gift_bg": gift_bg,
        "rarity_labels": RARITY_LABELS, "claimed_now": request.query_params.get("claimed") == "1",
    })


@router.post("/mail/{mail_id}/claim")
def mail_claim(mail_id: int, user: User = Depends(require_user), db: Session = Depends(get_db)):
    mail = mailbox.get_own(db, user, mail_id)
    if mail is None:
        raise HTTPException(status_code=404)
    mailbox.claim(db, user, mail)
    return RedirectResponse(f"/mail/{mail_id}?claimed=1", status_code=303)
