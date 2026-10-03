"""Counts of things waiting for an admin, shown as badges (profile icon, /admin toggle).

Round 1 has no queues yet: mosque requests arrive in round 4 (mosque_requests ->
app_mosques) and problem reports in round 3 (reports). Wire their pending counts in here
so every badge picks them up.
"""
from sqlalchemy.orm import Session


def pending_counts(db: Session) -> dict[str, int]:
    requests = 0   # round 4: mosque_requests with status "pending"
    reports = 0    # round 3: reports with status "open"
    return {"requests": requests, "reports": reports, "total": requests + reports}
