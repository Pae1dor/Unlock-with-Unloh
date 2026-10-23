"""Hadith, supplication and prayer texts from HadeethEnc.com (IslamHouse), Thai edition.

Each entry comes with the Arabic text, the Thai translation, who recorded it
("บันทึกโดย ...") and its grade (เศาะฮีห์ / หะซัน ...). The site states no licence for reusing
the content, so nothing is copied into our database: it is fetched when a page needs it,
kept in memory for a few hours so one visit does not hit their API many times, and every
page names the source and links back to it.

Which categories the app shows is fixed below. A visitor can only ask for those (and any
single hadith by number), never pass anything on to the API.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor

import httpx

BASE_URL = "https://hadeethenc.com/api/v1"
SITE_URL = "https://hadeethenc.com/th"
LANGUAGE = "th"

CACHE_SECONDS = 6 * 3600
MAX_CACHED = 600
PER_PAGE = 100  # the biggest category we show has 75

# ดุอาอ์ and remembrance (category 268 "ความเข้าใจเกี่ยวกับดุอาอ์และบทรำลึก" and its children).
DUA_CATEGORIES = (301, 302, 303, 306, 307, 308, 313, 311)
# หลักศรัทธา 6 ประการ: Allah, angels, scriptures, messengers, the last day, destiny.
FAITH_CATEGORIES = (59, 60, 61, 62, 63, 64)
# หลักปฏิบัติ 5 ประการ: "Islam is built on five" (Bukhari, Muslim) and the hadith defining Islam.
PILLAR_HADITHS = (65000, 4563)
# Prayer: conditions, ablution, pillars, how it is done, what is recited.
PRAYER_CATEGORIES = (460, 444, 461, 464, 465)

ALLOWED_CATEGORIES = frozenset(DUA_CATEGORIES + FAITH_CATEGORIES + PRAYER_CATEGORIES)

LOAD_ERROR = "ไม่สามารถโหลดเนื้อหาได้ กรุณาตรวจสอบการเชื่อมต่ออินเทอร์เน็ตแล้วลองใหม่"
NOT_FOUND_ERROR = "ไม่พบเนื้อหาที่ต้องการ"

_cache: dict[str, tuple[float, object]] = {}


class _NotFound(Exception):
    pass


def _request(path: str, **params) -> dict | list:
    response = httpx.get(
        f"{BASE_URL}{path}",
        params={"language": LANGUAGE, **params},
        timeout=15.0,
        follow_redirects=True,
    )
    if response.status_code == 404:
        raise _NotFound(path)
    response.raise_for_status()
    return response.json()


def _cached(key: str, load):
    """`load()`'s result, remembered for CACHE_SECONDS. Failures are never remembered."""
    now = time.monotonic()
    hit = _cache.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]
    value = load()
    if len(_cache) >= MAX_CACHED:
        for old in sorted(_cache, key=lambda k: _cache[k][0])[: MAX_CACHED // 4]:
            del _cache[old]
    _cache[key] = (now + CACHE_SECONDS, value)
    return value


def source_url(hadith_id: int) -> str:
    return f"{SITE_URL}/browse/hadith/{hadith_id}"


def _categories() -> dict[int, dict]:
    def load():
        rows = _request("/categories/list/")
        return {
            int(row["id"]): {
                "id": int(row["id"]),
                "title": row.get("title", ""),
                "count": int(row.get("hadeeths_count") or 0),
            }
            for row in rows
        }

    return _cached("categories", load)


def category(category_id: int) -> dict:
    """One category: {'ok', 'error', 'category': {id, title, count}, 'hadiths': [{id, title}]}."""
    failure = {"ok": False, "error": LOAD_ERROR, "category": None, "hadiths": []}
    if category_id not in ALLOWED_CATEGORIES:
        return {**failure, "error": NOT_FOUND_ERROR}

    def load():
        info = _categories().get(category_id) or {"id": category_id, "title": "", "count": 0}
        payload = _request("/hadeeths/list/", category_id=category_id, page=1, per_page=PER_PAGE)
        hadiths = [
            {"id": int(row["id"]), "title": row.get("title", "")} for row in payload.get("data") or []
        ]
        return {"ok": True, "error": None, "category": info, "hadiths": hadiths}

    try:
        return _cached(f"category:{category_id}", load)
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return failure


def groups(category_ids: tuple[int, ...]) -> dict:
    """Several categories at once, in the order given: {'ok', 'error', 'groups': [category...]}.
    `ok` is False only when none could be loaded; one failing group is left out."""
    with ThreadPoolExecutor(max_workers=min(8, len(category_ids))) as pool:
        results = list(pool.map(category, category_ids))
    loaded = [r for r in results if r["ok"]]
    if not loaded:
        return {"ok": False, "error": LOAD_ERROR, "groups": []}
    return {"ok": True, "error": None, "groups": loaded}


def hadith(hadith_id: int) -> dict:
    """One hadith in full: {'ok', 'error', 'hadith': {...}}."""
    failure = {"ok": False, "error": LOAD_ERROR, "hadith": None}

    def load():
        row = _request("/hadeeths/one/", id=hadith_id)
        if not isinstance(row, dict) or not row.get("hadeeth_ar"):
            raise _NotFound(str(hadith_id))
        return {
            "ok": True,
            "error": None,
            "hadith": {
                "id": hadith_id,
                "title": row.get("title", ""),
                "arabic": row.get("hadeeth_ar", ""),
                "thai": row.get("hadeeth", ""),
                "attribution": row.get("attribution", ""),
                "grade": row.get("grade", ""),
                "explanation": row.get("explanation", ""),
                "hints": [h for h in row.get("hints") or [] if h],
                "source_url": source_url(hadith_id),
            },
        }

    try:
        return _cached(f"hadith:{hadith_id}", load)
    except _NotFound:
        return {**failure, "error": NOT_FOUND_ERROR}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return failure


def faith_overview() -> dict:
    """What the หลักศาสนา tab lists: the 6 faith categories and the pillar hadiths' titles."""
    try:
        known = _categories()
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return {"ok": False, "error": LOAD_ERROR, "faith": [], "pillars": []}
    faith = [known[cid] for cid in FAITH_CATEGORIES if cid in known]
    pillars = []
    for hid in PILLAR_HADITHS:
        result = hadith(hid)
        if result["ok"]:
            pillars.append({"id": hid, "title": result["hadith"]["title"]})
    if not faith and not pillars:
        return {"ok": False, "error": LOAD_ERROR, "faith": [], "pillars": []}
    return {"ok": True, "error": None, "faith": faith, "pillars": pillars}
