"""Counts of things waiting for an admin, shown as badges (profile icon, /admin toggle)."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import MosqueRequest, Report


def pending_counts(db: Session) -> dict[str, int]:
    requests = db.scalar(select(func.count(MosqueRequest.id)).where(MosqueRequest.status == "pending")) or 0
    reports = db.scalar(select(func.count(Report.id)).where(Report.status == "open")) or 0
    return {"requests": requests, "reports": reports, "total": requests + reports}
