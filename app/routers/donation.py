"""บริจาค — campaigns with real generated QR codes, self-reported transfers, history."""
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user, require_user
from app.models import Donation, DonationCampaign, User
from app.templating import templates

router = APIRouter(tags=["donation"])


@router.get("/donation")
def campaign_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    campaigns = db.scalars(select(DonationCampaign).order_by(DonationCampaign.id)).all()
    return templates.TemplateResponse(
        request,
        "donation.html",
        {"user": user, "active": "home", "campaigns": campaigns},
    )


@router.get("/donation/history")
def donation_history(
    request: Request,
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    donations = db.scalars(
        select(Donation).where(Donation.user_id == user.id).order_by(Donation.created_at.desc())
    ).all()
    total = sum((Decimal(str(d.amount)) for d in donations), Decimal("0"))
    return templates.TemplateResponse(
        request,
        "donation_history.html",
        {"user": user, "active": "home", "donations": donations, "total": total},
    )


@router.get("/donation/{slug}")
def campaign_detail(
    request: Request,
    slug: str,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    campaign = db.scalar(select(DonationCampaign).where(DonationCampaign.slug == slug))
    if campaign is None:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"user": user, "active": "home", "title": "บริจาค", "message": "ไม่พบโครงการบริจาคนี้"},
            status_code=404,
        )
    return templates.TemplateResponse(
        request,
        "donation_detail.html",
        {"user": user, "active": "home", "campaign": campaign, "error": None},
    )


@router.post("/donation/{slug}/report")
def report_donation(
    request: Request,
    slug: str,
    amount: str = Form(...),
    note: str = Form(""),
    user: User = Depends(require_user),
    db: Session = Depends(get_db),
):
    campaign = db.scalar(select(DonationCampaign).where(DonationCampaign.slug == slug))
    if campaign is None:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"user": user, "active": "home", "title": "บริจาค", "message": "ไม่พบโครงการบริจาคนี้"},
            status_code=404,
        )

    try:
        value = Decimal(amount.replace(",", "").strip())
    except (InvalidOperation, AttributeError):
        value = Decimal("0")

    if value <= 0:
        return templates.TemplateResponse(
            request,
            "donation_detail.html",
            {
                "user": user,
                "active": "home",
                "campaign": campaign,
                "error": "กรุณากรอกจำนวนเงินให้ถูกต้อง",
            },
            status_code=400,
        )

    db.add(
        Donation(
            user_id=user.id,
            campaign_id=campaign.id,
            amount=value,
            note=(note or "").strip() or None,
        )
    )
    db.commit()
    return RedirectResponse("/donation/history?reported=1", status_code=303)
