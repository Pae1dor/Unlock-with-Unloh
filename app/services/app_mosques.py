"""Mosques added through the app (app_mosques), shown on the finder together with OSM.

Merging: an app mosque within MATCH_RADIUS_M of an OSM mosque is the same place. The app's
data wins (its pin, name and details), and the OSM entry is dropped. Which OSM mosque that
is gets cached in app_mosques.osm_ref, so the distance match runs once, not per request:
  None = not checked yet, "" = checked and none nearby, "osm:node/123" = that one.
The cache is (re)filled on approval, on an admin edit, and lazily for rows still None.

App mosques come from our own database, so they still show when the OSM data (nationwide
file or Overpass) is unavailable. Hidden rows (is_active=False) never appear here, but stay
in the table: check-ins and prayer logs point at "app:<id>".
"""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import mosque_ids
from app.models import AppMosque
from app.services import mosque_index

MATCH_RADIUS_M = 50.0
# ~110 m: app mosques just outside the map area can still claim an OSM pin inside it
EDGE_MARGIN_DEG = 0.001
SEARCH_LIMIT = 5


def to_api(m: AppMosque) -> dict:
    """Same shape as an OSM mosque on the finder, plus the details only the app has."""
    return {
        "id": m.mosque_id,              # "app:<id>"
        "name": m.name,
        "lat": m.lat,
        "lng": m.lng,
        "address": m.address or None,
        "opening_hours": m.opening_hours or None,
        "women": m.has_women_area,      # True / False / None (= not sure, not shown)
        "jumuah": m.has_jumuah,
    }


def match_osm(lat: float, lng: float) -> str | None:
    """osm_ref for a position: "osm:<id>" of an OSM mosque within 50 m, "" if none,
    or None when the nationwide OSM file isn't loaded (can't tell yet)."""
    if not mosque_index.available():
        return None
    box = EDGE_MARGIN_DEG
    best, best_d = None, MATCH_RADIUS_M
    for m in mosque_index.in_bbox(lat - box, lng - box, lat + box, lng + box):
        d = mosque_index.haversine_m(lat, lng, m["lat"], m["lng"])
        if d <= best_d:
            best, best_d = m, d
    return mosque_ids.from_osm(best["id"]) if best else ""


def _fill_osm_refs(db: Session, rows: list[AppMosque]) -> None:
    changed = False
    for row in rows:
        if row.osm_ref is None:
            ref = match_osm(row.lat, row.lng)
            if ref is not None:
                row.osm_ref = ref
                changed = True
    if changed:
        db.commit()


def _active(db: Session, s: float, w: float, n: float, e: float) -> list[AppMosque]:
    return list(db.scalars(select(AppMosque).where(
        AppMosque.is_active.is_(True),
        AppMosque.lat >= s, AppMosque.lat <= n, AppMosque.lng >= w, AppMosque.lng <= e,
    )).all())


def merge(osm: list[dict], app_rows: list[AppMosque]) -> list[dict]:
    """OSM + app mosques, one entry per place (app wins). Each OSM dict has a bare "id"."""
    claimed = {mosque_ids.to_osm(r.osm_ref) for r in app_rows if r.osm_ref}
    unchecked = [r for r in app_rows if r.osm_ref is None]   # OSM file not loaded: compare live
    out = []
    for m in osm:
        if m["id"] in claimed:
            continue
        if any(mosque_index.haversine_m(r.lat, r.lng, m["lat"], m["lng"]) <= MATCH_RADIUS_M for r in unchecked):
            continue
        out.append(m)
    return out


def in_bbox(db: Session, osm: list[dict], s: float, w: float, n: float, e: float) -> list[dict]:
    """The finder's 'map area' list: OSM mosques in the box merged with active app mosques."""
    m = EDGE_MARGIN_DEG
    nearby = _active(db, s - m, w - m, n + m, e + m)
    _fill_osm_refs(db, nearby)
    inside = [r for r in nearby if s <= r.lat <= n and w <= r.lng <= e]
    return merge(osm, nearby) + [to_api(r) for r in inside]


def nearest(db: Session, osm_ranked: list[dict], lat: float, lng: float, limit: int) -> list[dict]:
    """The `limit` closest places (OSM list already has `dist`), app mosques included."""
    rows = list(db.scalars(select(AppMosque).where(AppMosque.is_active.is_(True))).all())
    _fill_osm_refs(db, rows)
    apps = [{**to_api(r), "dist": round(mosque_index.haversine_m(lat, lng, r.lat, r.lng), 1)} for r in rows]
    ranked = sorted(merge(osm_ranked, rows) + apps, key=lambda x: x["dist"])
    return ranked[:limit]


def search(db: Session, q: str) -> list[dict]:
    """Active app mosques whose name contains `q` (anywhere in the country)."""
    q = q.strip()
    if len(q) < 2:
        return []
    pattern = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
    rows = db.scalars(
        select(AppMosque)
        .where(AppMosque.is_active.is_(True), func.lower(AppMosque.name).like(pattern.lower(), escape="\\"))
        .order_by(AppMosque.name)
        .limit(SEARCH_LIMIT)
    ).all()
    return [to_api(r) for r in rows]


def find(db: Session, api_id: str) -> dict | None:
    """Look up a mosque by its finder id ("node/1" or "app:3") for check-in: {id, name, lat, lng}.

    Hidden app mosques are not found (no new check-ins); OSM ones need the nationwide file.
    """
    app_id = mosque_ids.to_app(api_id)
    if app_id is not None:
        row = db.get(AppMosque, app_id)
        return to_api(row) if row is not None and row.is_active else None
    return mosque_index.find(api_id) if mosque_index.available() else None
