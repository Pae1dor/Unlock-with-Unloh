"""Qur'an data from the free alquran.cloud API.

Editions actually used (verified against GET /v1/edition?language=th — `th.thai`
is the only Thai translation the API exposes):
  * quran-uthmani  — Arabic, Uthmani script
  * th.thai        — Thai translation (King Fahad Quran Complex)

The 114-entry surah list and each fetched surah are cached in-process only (Quran text is
always fetched from an API, never stored by the app). If alquran.cloud doesn't answer,
api.quran.com is asked instead (same King Fahad Thai translation there, id 51).
"""
from __future__ import annotations

import re

import httpx

BASE_URL = "https://api.alquran.cloud/v1"
ARABIC_EDITION = "quran-uthmani"
THAI_EDITION = "th.thai"

# Thai transliterated surah names, index 0 == surah 1.
SURAH_NAMES_TH = [
    "อัลฟาติหะฮ์", "อัลบะเกาะเราะฮ์", "อาลิอิมรอน", "อันนิซาอ์", "อัลมาอิดะฮ์",
    "อัลอันอาม", "อัลอะอ์รอฟ", "อัลอันฟาล", "อัตเตาบะฮ์", "ยูนุส",
    "ฮูด", "ยูซุฟ", "อัรเราะอ์ด", "อิบรอฮีม", "อัลฮิจร์",
    "อันนะห์ล", "อัลอิสรออ์", "อัลกะฮ์ฟิ", "มัรยัม", "ฏอฮา",
    "อัลอันบิยาอ์", "อัลฮัจญ์", "อัลมุอ์มินูน", "อันนูร", "อัลฟุรกอน",
    "อัชชุอะรออ์", "อันนัมล์", "อัลเกาะศ็อศ", "อัลอันกะบูต", "อัรรูม",
    "ลุกมาน", "อัสสัจญ์ดะฮ์", "อัลอะห์ซาบ", "สะบะอ์", "ฟาฏิร",
    "ยาซีน", "อัศศ็อฟฟาต", "ศอด", "อัซซุมัร", "ฆอฟิร",
    "ฟุศศิลัต", "อัชชูรอ", "อัซซุครุฟ", "อัดดุคอน", "อัลญาษิยะฮ์",
    "อัลอะห์กอฟ", "มุฮัมมัด", "อัลฟัตห์", "อัลฮุญุรอต", "กอฟ",
    "อัซซาริยาต", "อัฏฏูร", "อันนัจม์", "อัลเกาะมัร", "อัรเราะห์มาน",
    "อัลวากิอะฮ์", "อัลฮะดีด", "อัลมุญาดะละฮ์", "อัลฮัชร์", "อัลมุมตะฮะนะฮ์",
    "อัศศ็อฟ", "อัลญุมุอะฮ์", "อัลมุนาฟิกูน", "อัตตะฆอบุน", "อัฏเฏาะลาก",
    "อัตตะห์รีม", "อัลมุลก์", "อัลเกาะลัม", "อัลฮากเกาะฮ์", "อัลมะอาริจ",
    "นูห์", "อัลญินน์", "อัลมุซซัมมิล", "อัลมุดดัษษิร", "อัลกิยามะฮ์",
    "อัลอินซาน", "อัลมุรซะลาต", "อันนะบะอ์", "อันนาซิอาต", "อะบะสะ",
    "อัตตักวีร", "อัลอินฟิฏอร", "อัลมุฏ็อฟฟิฟีน", "อัลอินชิกอก", "อัลบุรูจ",
    "อัฏฏอริก", "อัลอะอ์ลา", "อัลฆอชิยะฮ์", "อัลฟัจร์", "อัลบะลัด",
    "อัชชัมส์", "อัลลัยล์", "อัฎฎุฮา", "อัชชัรห์", "อัตตีน",
    "อัลอะลัก", "อัลก็อดร์", "อัลบัยยินะฮ์", "อัซซัลซะละฮ์", "อัลอาดิยาต",
    "อัลกอริอะฮ์", "อัตตะกาษุร", "อัลอัศร์", "อัลฮุมะซะฮ์", "อัลฟีล",
    "กุร็อยช์", "อัลมาอูน", "อัลเกาษัร", "อัลกาฟิรูน", "อันนัศร์",
    "อัลมะสัด", "อัลอิคลาศ", "อัลฟะลัก", "อันนาส",
]

REVELATION_TH = {"Meccan": "มักกียะฮ์", "Medinan": "มะดะนียะฮ์"}

BOM = "\ufeff"  # zero-width no-break space the API prefixes to the first ayah

# Fallback source when alquran.cloud doesn't answer.
QURAN_COM_URL = "https://api.quran.com/api/v4"
QURAN_COM_THAI = 51  # "Thai Translation (King Fahad Quran Complex)" — same as th.thai
QURAN_COM_REVELATION = {"makkah": "มักกียะฮ์", "madinah": "มะดะนียะฮ์"}
PRIMARY_TIMEOUT = 8.0  # fail over quickly instead of making the page hang

_TAG = re.compile(r"<sup[^>]*>.*?</sup>|<[^>]+>", re.S)  # footnote markers / tags in translations

# api.alquran.cloud also publishes an IPv6 address that some networks can't reach; httpx may
# try it first and hang until the timeout. Connecting over IPv4 avoids that.
_http = httpx.Client(transport=httpx.HTTPTransport(local_address="0.0.0.0"))

_surah_list_cache: list[dict] | None = None
_surah_cache: dict[int, dict] = {}


def thai_name(number: int) -> str:
    if 1 <= number <= len(SURAH_NAMES_TH):
        return SURAH_NAMES_TH[number - 1]
    return f"ซูเราะฮ์ที่ {number}"


def _list_from_alquran_cloud() -> list[dict]:
    response = _http.get(f"{BASE_URL}/surah", timeout=PRIMARY_TIMEOUT)
    response.raise_for_status()
    surahs = []
    for item in response.json().get("data") or []:
        number = item.get("number")
        if not number:
            continue
        surahs.append({
            "number": number,
            "name_th": thai_name(number),
            "name_ar": item.get("name", ""),
            "name_en": item.get("englishName", ""),
            "meaning_en": item.get("englishNameTranslation", ""),
            "ayah_count": item.get("numberOfAyahs", 0),
            "revelation_th": REVELATION_TH.get(item.get("revelationType", ""), ""),
        })
    return surahs


def _list_from_quran_com() -> list[dict]:
    response = _http.get(f"{QURAN_COM_URL}/chapters", params={"language": "en"}, timeout=15.0)
    response.raise_for_status()
    surahs = []
    for item in response.json().get("chapters") or []:
        number = item.get("id")
        if not number:
            continue
        surahs.append({
            "number": number,
            "name_th": thai_name(number),
            "name_ar": item.get("name_arabic", ""),
            "name_en": item.get("name_simple", ""),
            "meaning_en": (item.get("translated_name") or {}).get("name", ""),
            "ayah_count": item.get("verses_count", 0),
            "revelation_th": QURAN_COM_REVELATION.get(item.get("revelation_place", ""), ""),
        })
    return surahs


def get_surah_list() -> dict:
    """Return {'ok': bool, 'surahs': [...], 'error': str|None}.

    In-memory cache -> alquran.cloud -> api.quran.com.
    """
    global _surah_list_cache
    if _surah_list_cache is not None:
        return {"ok": True, "surahs": _surah_list_cache, "error": None}

    surahs = []
    for source in (_list_from_alquran_cloud, _list_from_quran_com):
        try:
            surahs = source()
        except (httpx.HTTPError, ValueError):
            surahs = []
        if surahs:
            break

    if not surahs:
        return {
            "ok": False,
            "surahs": [],
            "error": "ไม่สามารถโหลดรายชื่อซูเราะฮ์ได้ กรุณาตรวจสอบการเชื่อมต่ออินเทอร์เน็ตแล้วลองใหม่",
        }

    _surah_list_cache = surahs
    return {"ok": True, "surahs": surahs, "error": None}


def _surah_from_alquran_cloud(number: int) -> dict | None:
    editions = f"{ARABIC_EDITION},{THAI_EDITION}"
    try:
        response = _http.get(
            f"{BASE_URL}/surah/{number}/editions/{editions}", timeout=PRIMARY_TIMEOUT
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None

    blocks = {}
    for block in payload.get("data") or []:
        identifier = (block.get("edition") or {}).get("identifier")
        if identifier:
            blocks[identifier] = block

    arabic = blocks.get(ARABIC_EDITION)
    if not arabic:
        return {
            "ok": False,
            "error": f"ไม่พบซูเราะฮ์ที่ {number}",
            "surah": None,
            "ayahs": [],
        }

    thai = blocks.get(THAI_EDITION) or {}
    thai_ayahs = thai.get("ayahs") or []

    ayahs = []
    for index, ayah in enumerate(arabic.get("ayahs") or []):
        translation = thai_ayahs[index].get("text", "") if index < len(thai_ayahs) else ""
        ayahs.append(
            {
                "number": ayah.get("numberInSurah", index + 1),
                # The API prefixes the first ayah with a BOM; it renders as a stray glyph.
                "arabic": ayah.get("text", "").lstrip(BOM),
                "thai": translation.lstrip(BOM),
            }
        )

    result = {
        "ok": True,
        "error": None,
        "surah": {
            "number": arabic.get("number", number),
            "name_th": thai_name(arabic.get("number", number)),
            "name_ar": arabic.get("name", ""),
            "name_en": arabic.get("englishName", ""),
            "meaning_en": arabic.get("englishNameTranslation", ""),
            "ayah_count": arabic.get("numberOfAyahs", len(ayahs)),
            "revelation_th": REVELATION_TH.get(arabic.get("revelationType", ""), ""),
        },
        "ayahs": ayahs,
    }
    return result


def _surah_from_quran_com(number: int) -> dict | None:
    meta = next((x for x in get_surah_list()["surahs"] if x["number"] == number), None)
    if meta is None:
        return None
    ayahs, page = [], 1
    try:
        while page:
            response = _http.get(
                f"{QURAN_COM_URL}/verses/by_chapter/{number}",
                params={"translations": QURAN_COM_THAI, "fields": "text_uthmani", "per_page": 50, "page": page},
                timeout=15.0,
            )
            response.raise_for_status()
            data = response.json()
            for verse in data.get("verses") or []:
                translations = verse.get("translations") or []
                thai = _TAG.sub("", translations[0].get("text", "")) if translations else ""
                ayahs.append({
                    "number": verse.get("verse_number"),
                    "arabic": verse.get("text_uthmani", ""),
                    "thai": " ".join(thai.split()),
                })
            page = (data.get("pagination") or {}).get("next_page")
    except (httpx.HTTPError, ValueError):
        return None
    if not ayahs:
        return None
    return {"ok": True, "error": None, "surah": dict(meta), "ayahs": ayahs}


def get_surah(number: int) -> dict:
    """One surah, Arabic + Thai translation (text only — the app plays no audio).

    In-memory cache -> alquran.cloud -> api.quran.com.
    """
    if number in _surah_cache:
        return _surah_cache[number]
    result = _surah_from_alquran_cloud(number) or _surah_from_quran_com(number)
    if not result:
        return {
            "ok": False,
            "error": "ไม่สามารถโหลดเนื้อหาซูเราะฮ์ได้ กรุณาตรวจสอบการเชื่อมต่ออินเทอร์เน็ตแล้วลองใหม่",
            "surah": None,
            "ayahs": [],
        }
    if result.get("ok"):
        _surah_cache[number] = result
    return result
