"""Mosques from OpenStreetMap (Overpass API), cached per map tile.

The mosque finder asks for the area the map shows (a bbox). We snap it to a grid of
TILE_DEG x TILE_DEG tiles and answer from the cache when every tile is younger than
CACHE_TTL. Missing or expired tiles are fetched with ONE Overpass query covering them,
trying the mirrors in order. If every mirror fails, tiles we fetched before are served
anyway with `stale: true`.

The cache lives in memory and in JSON files under .cache/overpass/, so a server restart
doesn't throw it away. Nothing goes into the database.
"""
from __future__ import annotations

import json
import math
import threading
import time
from pathlib import Path

import httpx

from app.config import CACHE_DIR, UPSTREAM_USER_AGENT
from app.services.ratelimit import overpass_limiter

TILE_DEG = 0.05                 # ~5.5 km
CACHE_TTL = 24 * 3600           # seconds
MAX_TILES = 64                  # the finder only asks at zoom >= 12, which is ~20 tiles on a phone
MIRRORS = [
    "https://overpass-api.de/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
MIRROR_TIMEOUT = 10.0           # seconds per mirror
FETCH_LOCK_WAIT = 40.0          # how long a request waits for another request's fetch to finish
UNNAMED = "มัสยิด (ไม่มีชื่อ)"

_TILE_DIR = CACHE_DIR / "overpass"
# tile key -> (fetched_at epoch seconds, [mosque, ...])
_memory: dict[str, tuple[float, list[dict]]] = {}
_memory_lock = threading.Lock()
# One Overpass fetch at a time; others wait and then usually find the tiles cached.
_fetch_lock = threading.Lock()


class BBoxError(ValueError):
    """The bbox parameter is malformed or covers too much ground."""


class UpstreamError(RuntimeError):
    """Every Overpass mirror failed and there is nothing cached to fall back on."""


def parse_bbox(text: str) -> tuple[float, float, float, float]:
    """'south,west,north,east' -> floats, validated."""
    try:
        s, w, n, e = (float(part) for part in text.split(","))
    except ValueError:
        raise BBoxError("bbox must be 'south,west,north,east'") from None
    if not all(math.isfinite(v) for v in (s, w, n, e)):
        raise BBoxError("bbox values must be numbers")
    if not (-90 <= s < n <= 90 and -180 <= w < e <= 180):
        raise BBoxError("bbox is out of range or south/west are not below north/east")
    return s, w, n, e


def _tile_index(value: float) -> int:
    return math.floor(value / TILE_DEG)


def _tiles_for(s: float, w: float, n: float, e: float) -> list[tuple[int, int]]:
    return [
        (ty, tx)
        for ty in range(_tile_index(s), _tile_index(n) + 1)
        for tx in range(_tile_index(w), _tile_index(e) + 1)
    ]


def _key(tile: tuple[int, int]) -> str:
    return f"{tile[0]}_{tile[1]}"


def _tile_path(key: str) -> Path:
    return _TILE_DIR / f"{key}.json"


def _load(key: str) -> tuple[float, list[dict]] | None:
    with _memory_lock:
        if key in _memory:
            return _memory[key]
    try:
        raw = json.loads(_tile_path(key).read_text(encoding="utf-8"))
        entry = (float(raw["fetched_at"]), list(raw["mosques"]))
    except (OSError, ValueError, KeyError, TypeError):
        return None
    with _memory_lock:
        _memory[key] = entry
    return entry


def _store(key: str, fetched_at: float, mosques: list[dict]) -> None:
    with _memory_lock:
        _memory[key] = (fetched_at, mosques)
    try:
        _TILE_DIR.mkdir(parents=True, exist_ok=True)
        tmp = _tile_path(key).with_suffix(".tmp")
        tmp.write_text(json.dumps({"fetched_at": fetched_at, "mosques": mosques}, ensure_ascii=False), encoding="utf-8")
        tmp.replace(_tile_path(key))
    except OSError:
        pass  # the in-memory copy still works; the file is only for surviving restarts


def _to_mosque(element: dict) -> dict | None:
    tags = element.get("tags") or {}
    # nodes carry lat/lon; ways and relations only have the centre Overpass computed
    lat = element.get("lat", (element.get("center") or {}).get("lat"))
    lng = element.get("lon", (element.get("center") or {}).get("lon"))
    if lat is None or lng is None or "type" not in element or "id" not in element:
        return None
    return {
        "id": f"{element['type']}/{element['id']}",
        "name": tags.get("name:th") or tags.get("name") or UNNAMED,
        "lat": float(lat),
        "lng": float(lng),
    }


def _query_overpass(s: float, w: float, n: float, e: float) -> list[dict]:
    query = (
        "[out:json][timeout:25];"
        f'nwr["amenity"="place_of_worship"]["religion"="muslim"]({s},{w},{n},{e});'
        "out center tags;"
    )
    for url in MIRRORS:
        if not overpass_limiter.acquire(max_wait=MIRROR_TIMEOUT):
            break
        try:
            response = httpx.post(
                url,
                data={"data": query},
                headers={"User-Agent": UPSTREAM_USER_AGENT},
                timeout=MIRROR_TIMEOUT,
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            continue
        # Overpass reports a query that ran out of time/memory as HTTP 200 with a "remark"
        # and possibly partial results; caching those would hide mosques for a day.
        if "runtime error" in str(payload.get("remark", "")).lower():
            continue
        mosques = [m for m in map(_to_mosque, payload.get("elements") or []) if m]
        return mosques
    raise UpstreamError("all Overpass mirrors failed")


def nearby(s: float, w: float, n: float, e: float) -> dict:
    """Mosques inside the bbox: {'mosques': [...], 'stale': bool}."""
    tiles = _tiles_for(s, w, n, e)
    if len(tiles) > MAX_TILES:
        raise BBoxError("area too large; zoom in")
    keys = [_key(t) for t in tiles]

    def expired(entry):
        return entry is None or time.time() - entry[0] > CACHE_TTL

    entries = {k: _load(k) for k in keys}
    stale = False
    if any(expired(entries[k]) for k in keys):
        got_lock = _fetch_lock.acquire(timeout=FETCH_LOCK_WAIT)
        try:
            # Another request may have fetched these tiles while we waited.
            entries = {k: _load(k) for k in keys}
            missing = [t for t in tiles if expired(entries[_key(t)])]
            if missing and got_lock:
                ys = [t[0] for t in missing]
                xs = [t[1] for t in missing]
                box = (min(ys) * TILE_DEG, min(xs) * TILE_DEG, (max(ys) + 1) * TILE_DEG, (max(xs) + 1) * TILE_DEG)
                try:
                    found = _query_overpass(*box)
                except UpstreamError:
                    stale = True
                else:
                    now = time.time()
                    buckets: dict[str, list[dict]] = {}
                    for m in found:
                        buckets.setdefault(_key((_tile_index(m["lat"]), _tile_index(m["lng"]))), []).append(m)
                    # Every tile inside the queried box is now fresh, including empty ones.
                    for ty in range(min(ys), max(ys) + 1):
                        for tx in range(min(xs), max(xs) + 1):
                            key = _key((ty, tx))
                            _store(key, now, buckets.get(key, []))
                            if key in entries:
                                entries[key] = _memory[key]
            elif missing:
                stale = True  # waited too long for the other fetch; serve what we have
        finally:
            if got_lock:
                _fetch_lock.release()

    if stale and all(entries[k] is None for k in keys):
        raise UpstreamError("Overpass unavailable and nothing cached for this area")

    seen: set[str] = set()
    mosques = []
    for k in keys:
        entry = entries[k]
        for m in entry[1] if entry else []:
            if m["id"] not in seen and s <= m["lat"] <= n and w <= m["lng"] <= e:
                seen.add(m["id"])
                mosques.append(m)
    return {"mosques": mosques, "stale": stale}
