"""Qur'an data from the free alquran.cloud API.

Editions actually used (verified against GET /v1/edition?language=th — `th.thai`
is the only Thai translation the API exposes):
  * quran-uthmani  — Arabic, Uthmani script
  * th.thai        — Thai translation (King Fahad Quran Complex)
  * ar.alafasy     — per-ayah audio (Mishary Alafasy), gives an .mp3 url per verse

The 114-entry surah list and each fetched surah are cached in-process.
"""
from __future__ import annotations

import httpx

BASE_URL = "https://api.alquran.cloud/v1"
ARABIC_EDITION = "quran-uthmani"
THAI_EDITION = "th.thai"
AUDIO_EDITION = "ar.alafasy"

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

_surah_list_cache: list[dict] | None = None
_surah_cache: dict[int, dict] = {}


def thai_name(number: int) -> str:
    if 1 <= number <= len(SURAH_NAMES_TH):
        return SURAH_NAMES_TH[number - 1]
    return f"ซูเราะฮ์ที่ {number}"


def get_surah_list() -> dict:
    """Return {'ok': bool, 'surahs': [...], 'error': str|None}. Cached after first success."""
    global _surah_list_cache
    if _surah_list_cache is not None:
        return {"ok": True, "surahs": _surah_list_cache, "error": None}

    try:
        response = httpx.get(f"{BASE_URL}/surah", timeout=15.0, follow_redirects=True)
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return {
            "ok": False,
            "surahs": [],
            "error": "ไม่สามารถโหลดรายชื่อซูเราะฮ์ได้ กรุณาตรวจสอบการเชื่อมต่ออินเทอร์เน็ตแล้วลองใหม่",
        }

    surahs = []
    for item in payload.get("data") or []:
        number = item.get("number")
        if not number:
            continue
        surahs.append(
            {
                "number": number,
                "name_th": thai_name(number),
                "name_ar": item.get("name", ""),
                "name_en": item.get("englishName", ""),
                "meaning_en": item.get("englishNameTranslation", ""),
                "ayah_count": item.get("numberOfAyahs", 0),
                "revelation_th": REVELATION_TH.get(item.get("revelationType", ""), ""),
            }
        )

    if not surahs:
        return {"ok": False, "surahs": [], "error": "ไม่พบข้อมูลซูเราะฮ์จากบริการภายนอก"}

    _surah_list_cache = surahs
    return {"ok": True, "surahs": surahs, "error": None}


def get_surah(number: int) -> dict:
    """Fetch one surah with Arabic text, Thai translation and per-ayah audio urls."""
    if number in _surah_cache:
        return _surah_cache[number]

    editions = f"{ARABIC_EDITION},{THAI_EDITION},{AUDIO_EDITION}"
    try:
        response = httpx.get(
            f"{BASE_URL}/surah/{number}/editions/{editions}", timeout=20.0, follow_redirects=True
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return {
            "ok": False,
            "error": "ไม่สามารถโหลดเนื้อหาซูเราะฮ์ได้ กรุณาตรวจสอบการเชื่อมต่ออินเทอร์เน็ตแล้วลองใหม่",
            "surah": None,
            "ayahs": [],
        }

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
    audio = blocks.get(AUDIO_EDITION) or {}
    thai_ayahs = thai.get("ayahs") or []
    audio_ayahs = audio.get("ayahs") or []

    ayahs = []
    for index, ayah in enumerate(arabic.get("ayahs") or []):
        translation = thai_ayahs[index].get("text", "") if index < len(thai_ayahs) else ""
        audio_url = audio_ayahs[index].get("audio") if index < len(audio_ayahs) else None
        ayahs.append(
            {
                "number": ayah.get("numberInSurah", index + 1),
                # The API prefixes the first ayah with a BOM; it renders as a stray glyph.
                "arabic": ayah.get("text", "").lstrip(BOM),
                "thai": translation.lstrip(BOM),
                "audio": audio_url,
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
    _surah_cache[number] = result
    return result
