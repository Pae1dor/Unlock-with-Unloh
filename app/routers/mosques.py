"""ค้นหามัสยิด — Leaflet map plus a distance-sorted list."""
from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.deps import get_current_user
from app.models import Mosque, User
from app.schemas import MosqueOut
from app.templating import templates

router = APIRouter(tags=["mosques"])


@router.get("/mosques")
def mosque_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User | None = Depends(get_current_user),
):
    mosques = db.scalars(select(Mosque).order_by(Mosque.name)).all()
    return templates.TemplateResponse(
        request,
        "mosques.html",
        {"user": user, "active": "home", "mosques": mosques},
    )


@router.get("/api/mosques", response_model=list[MosqueOut])
def mosque_api(db: Session = Depends(get_db)):
    mosques = db.scalars(select(Mosque).order_by(Mosque.name)).all()
    return [
        MosqueOut(
            id=m.id, name=m.name, address=m.address, phone=m.phone, lat=m.lat, lng=m.lng
        )
        for m in mosques
    ]
