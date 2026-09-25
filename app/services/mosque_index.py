"""Every mosque in Thailand from OpenStreetMap, downloaded once a day.

A background job fetches them all with one Overpass query into
.cache/overpass/th_mosques.json. /api/mosques/nearby and /api/mosques/nearest answer from
that file (held in memory) by filtering locally, so browsing the map never waits on
Overpass. Until the first download has finished, overpass.py's per-tile cache is the fallback.
If a download fails, the previous file keeps being served.
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time

import httpx

from app.config import CACHE_DIR, UPSTREAM_USER_AGENT
from app.services import overpass
from app.services.ratelimit import overpass_limiter

# A child of uvicorn's logger so the download report shows up in the server console.
log = logging.getLogger("uvicorn.error.mosque_index")

DATA_FILE = CACHE_DIR / "overpass" / "th_mosques.json"
REFRESH_EVERY = 24 * 3600        # seconds between successful downloads
RETRY_FAILED_AFTER = 3600        # after a failed round, try again in an hour
STALE_AFTER = 48 * 3600          # flag data as stale once two refreshes have been missed
QUERY = (
    "[out:json][timeout:180];"
    'area["ISO3166-1"="TH"]->.th;'
    'nwr["amenity"="place_of_worship"]["religion"="muslim"](area.th);'
    "out center tags;"
)
MIRROR_TIMEOUT = 200.0           # Overpass itself gives up after 180 s
ROUNDS = 3                       # each round tries every mirror once
ROUND_DELAYS = (60, 300)         # pause before round 2 and round 3
# A download with far fewer mosques than the file we already have is treated as broken
# (e.g. a mirror with an incomplete database) and discarded.
MIN_KEEP_RATIO = 0.8

_state_lock = threading.Lock()
_fetched_at = 0.0
_mosques: list[dict] = []
_stop = threading.Event()
_thread: threading.Thread | None = None


# ---------- reading ----------
def available() -> bool:
    return bool(_mosques)


def is_stale() -> bool:
    return time.time() - _fetched_at > STALE_AFTER


def info() -> dict:
    size = DATA_FILE.stat().st_size if DATA_FILE.exists() else 0
    return {"count": len(_mosques), "fetched_at": _fetched_at, "file_bytes": size}


def in_bbox(s: float, w: float, n: float, e: float) -> list[dict]:
    return [m for m in _mosques if s <= m["lat"] <= n and w <= m["lng"] <= e]


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lng2 - lng1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371000 * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def nearest(lat: float, lng: float, limit: int) -> list[dict]:
    """The `limit` closest mosques, each with `dist` in metres."""
    ranked = sorted(_mosques, key=lambda m: haversine_m(lat, lng, m["lat"], m["lng"]))[:limit]
    return [{**m, "dist": round(haversine_m(lat, lng, m["lat"], m["lng"]), 1)} for m in ranked]


def find(osm_id: str) -> dict | None:
    return next((m for m in _mosques if m["id"] == osm_id), None)


def load() -> bool:
    """Load the saved file into memory. False if there is none (or it is unreadable)."""
    global _fetched_at, _mosques
    try:
        raw = json.loads(DATA_FILE.read_text(encoding="utf-8"))
        fetched_at, mosques = float(raw["fetched_at"]), list(raw["mosques"])
    except (OSError, ValueError, KeyError, TypeError):
        return False
    with _state_lock:
        _fetched_at, _mosques = fetched_at, mosques
    return bool(mosques)


# ---------- downloading ----------
def _download_once(min_count: int) -> list[dict] | None:
    """One pass over the mirrors; None if none of them delivered a complete answer."""
    for url in overpass.MIRRORS:
        if not overpass_limiter.acquire(max_wait=60):
            return None
        started = time.monotonic()
        try:
            response = httpx.post(
                url,
                data={"data": QUERY},
                headers={"User-Agent": UPSTREAM_USER_AGENT},
                timeout=MIRROR_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            log.warning("Thailand mosque download: %s failed after %.0fs (%s)", url, time.monotonic() - started, exc)
            continue
        if "runtime error" in str(payload.get("remark", "")).lower():
            log.warning("Thailand mosque download: %s returned a partial result (%s)", url, payload.get("remark"))
            continue
        seen: set[str] = set()
        mosques = []
        for m in map(overpass.to_mosque, payload.get("elements") or []):
            if m and m["id"] not in seen:
                seen.add(m["id"])
                mosques.append(m)
        if len(mosques) < min_count:
            log.warning("Thailand mosque download: %s returned only %d mosques (need %d); trying the next mirror",
                        url, len(mosques), min_count)
            continue
        log.info("Thailand mosque download: %d mosques from %s in %.0fs", len(mosques), url, time.monotonic() - started)
        return mosques
    return None


def refresh(sleep=time.sleep) -> bool:
    """Download everything and replace the file. On failure the old file stays in use."""
    global _fetched_at, _mosques
    for round_no in range(ROUNDS):
        if round_no:
            sleep(ROUND_DELAYS[min(round_no - 1, len(ROUND_DELAYS) - 1)])
            if _stop.is_set():
                return False
        mosques = _download_once(min_count=max(1, math.ceil(len(_mosques) * MIN_KEEP_RATIO)))
        if mosques is None:
            continue
        now = time.time()
        try:
            DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
            tmp = DATA_FILE.with_suffix(".tmp")
            tmp.write_text(json.dumps({"fetched_at": now, "count": len(mosques), "mosques": mosques},
                                      ensure_ascii=False), encoding="utf-8")
            tmp.replace(DATA_FILE)
        except OSError as exc:
            log.warning("Thailand mosque download: could not save %s (%s); using it from memory", DATA_FILE, exc)
        with _state_lock:
            _fetched_at, _mosques = now, mosques
        log.info("Thailand mosques saved: %d mosques, %.1f KB", len(mosques),
                 DATA_FILE.stat().st_size / 1024 if DATA_FILE.exists() else 0)
        return True
    log.warning("Thailand mosque download failed; %s", "keeping the previous file" if _mosques else "no data yet")
    return False


def _run() -> None:
    load()
    while not _stop.is_set():
        due = _fetched_at + REFRESH_EVERY
        if time.time() >= due:
            ok = refresh(sleep=lambda s: _stop.wait(s))
            wait = REFRESH_EVERY if ok else RETRY_FAILED_AFTER
        else:
            wait = due - time.time()
        _stop.wait(max(1.0, wait))


def start() -> None:
    """Load the saved file now and keep it fresh in a background thread."""
    global _thread
    load()
    if _thread and _thread.is_alive():
        return
    _stop.clear()
    _thread = threading.Thread(target=_run, name="th-mosque-refresh", daemon=True)
    _thread.start()


def stop() -> None:
    _stop.set()
