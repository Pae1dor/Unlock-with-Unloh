"""Data fixes run on every startup, right after create_all (see database.init_db).

The project has no migration tool: new tables come from create_all, and the few changes
to existing *data* live here. Every step is idempotent, so running it again is a no-op.
Nothing here drops tables, columns or rows.
"""
import logging

from sqlalchemy import and_, literal, not_, or_, update
from sqlalchemy.orm import Session

from app.mosque_ids import APP_PREFIX, OSM_PREFIX
from app.models import MosqueCheckin, PrayerLog
from app.services import roles

log = logging.getLogger("uvicorn.error")


def _unprefixed(column):
    return and_(column.is_not(None),
                not_(or_(column.startswith(OSM_PREFIX), column.startswith(APP_PREFIX))))


def prefix_mosque_ids(db: Session) -> int:
    """Stored OSM ids "node/123" -> "osm:node/123" (app/mosque_ids.py)."""
    changed = 0
    for column in (MosqueCheckin.osm_id, PrayerLog.mosque_id):
        result = db.execute(
            update(column.class_).where(_unprefixed(column)).values({column.key: literal(OSM_PREFIX) + column})
        )
        changed += result.rowcount or 0
    db.commit()
    return changed


def run(db: Session) -> None:
    admins = roles.backfill_from_legacy_flag(db)
    if admins:
        log.info("user_roles: %d admin(s) carried over from users.is_admin", admins)
    prefixed = prefix_mosque_ids(db)
    if prefixed:
        log.info("mosque ids: %d stored id(s) given the osm: prefix", prefixed)
