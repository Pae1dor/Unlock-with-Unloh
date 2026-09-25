"""Place search in Thailand via Nominatim (OpenStreetMap), for the mosque finder's search box.

Calls go through the server so we can send a proper User-Agent, keep the whole app under
Nominatim's 1 request/second limit, and cache repeated searches.
"""
from __future__ import annotations

import threading
import time
from collections import OrderedDict

import httpx

from app.config import UPSTREAM_USER_AGENT
from app.services.ratelimit import nominatim_limiter

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
REQUEST_TIMEOUT = 8.0
MAX_WAIT_FOR_SLOT = 3.0
CACHE_TTL = 24 * 3600
CACHE_SIZE = 500

_cache: OrderedDict[str, tuple[float, list[dict]]] = OrderedDict()
_cache_lock = threading.Lock()


class GeocodeBusy(RuntimeError):
    """Too many searches queued; the caller should try again shortly."""


class GeocodeError(RuntimeError):
    """Nominatim could not be reached or answered with an error."""


def _short_label(display_name: str) -> str:
    # "Bang Rak, Bangkok, 10500, Thailand" -> "Bang Rak, Bangkok"
    parts = [p.strip() for p in display_name.split(",") if p.strip()]
    parts = [p for p in parts if not p.isdigit() and p not in ("ประเทศไทย", "Thailand")]
    return ", ".join(parts[:3])


def search(query: str) -> list[dict]:
    """Up to 5 places in Thailand: [{'name', 'label', 'lat', 'lng'}]."""
    key = " ".join(query.lower().split())
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < CACHE_TTL:
            _cache.move_to_end(key)
            return hit[1]

    if not nominatim_limiter.acquire(max_wait=MAX_WAIT_FOR_SLOT):
        raise GeocodeBusy()
    try:
        response = httpx.get(
            NOMINATIM_URL,
            params={
                "q": query,
                "format": "jsonv2",
                "countrycodes": "th",
                "limit": 5,
                "accept-language": "th",
            },
            headers={"User-Agent": UPSTREAM_USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        rows = response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise GeocodeError(str(exc)) from exc

    results = []
    for row in rows if isinstance(rows, list) else []:
        try:
            display = row.get("display_name") or ""
            results.append({
                "name": row.get("name") or display.split(",")[0].strip(),
                "label": _short_label(display),
                "lat": float(row["lat"]),
                "lng": float(row["lon"]),
            })
        except (KeyError, TypeError, ValueError):
            continue

    with _cache_lock:
        _cache[key] = (time.time(), results)
        _cache.move_to_end(key)
        while len(_cache) > CACHE_SIZE:
            _cache.popitem(last=False)
    return results
