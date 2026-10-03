"""Character outfits (ชุดตัวละคร).

Each outfit is one full-body picture of the character already wearing it — like the
pre-rendered player cards in a football game — so switching outfits is just switching
images. Every image should share the same pose, canvas size and transparent background.

This is a test catalog kept in code; new outfits = drop an image in static/img and add a row.
"""

# The character before any outfit is chosen ("ตัวการ์ตูนเริ่มต้น"), per avatar style.
# Same canvas as the outfit images (1024x1536, transparent), so it stands on any background.
DEFAULT_CHARACTER = {
    "male": "/static/img/main.png",
    "female": "/static/img/main2.png",
}

OUTFITS = {
    "thobe-white": {
        "name": "ชุดโต๊ปขาว",
        "image": "/static/img/Test1.png",
        "gender": "male",
        "rarity": "common",
    },

    "street-flame": {
        "name": "เศรษฐีดูไบ",
        "image": "/static/img/Test2.png",
        "gender": "male",
       "rarity": "limited",
    },
    # Reward: unlocked for good the first time a user logs all five prayers in one day.
    "musalli": {
        "name": "ชุดมุศ็อลลี",
        "image": "/static/img/freeforuser.png",
        "gender": "male",
        "rarity": "rare",
        "unlock": "five_prayers",
    },
        "Girls-Muslium": {
                "name": "ชุดโต๊ปขาว",
                "image": "/static/img/GirlsMuslium.png",
                "gender": "female",
                "rarity": "common",
            },
}

# Backgrounds behind the character. "image": None = the soft garden scene drawn in CSS
# (.stage / .mascot-card--outfit in style.css). Image backgrounds: square, ~1200x1200,
# keep the centre plain (the character stands there).
BACKGROUNDS = {
    "scene": {
        "name": "สวนสีเขียว (เดิม)",
        "image": None,
        "rarity": "common",
    },
    "haram": {
        "name": "มัสยิดอัลฮะรอม",
        "image": "/static/img/BG1.png",
        "rarity": "limited",
    },
}
DEFAULT_BACKGROUND = "scene"

# Hidden from the wardrobe (and taken off anyone wearing them) until there is a way to earn them.
HIDDEN_RARITIES = {"limited"}

# How a locked outfit is earned -> the hint shown on its card.
UNLOCK_HINTS = {
    "five_prayers": "ละหมาดครบ 5 เวลาใน 1 วัน",
}

RARITY_LABELS = {
    "common": "ทั่วไป",
    "rare": "หายาก",
    "limited": "ลิมิเต็ด",
}


def is_wearable(key: str, outfit: dict, unlocked: set[str]) -> bool:
    """Shown in the wardrobe and earned (if it has to be earned). A hidden rarity (e.g. limited)
    is still wearable by someone who owns it — given as a gift from the mailbox."""
    if outfit["rarity"] in HIDDEN_RARITIES:
        return key in unlocked
    return "unlock" not in outfit or key in unlocked


def outfits_for(avatar_style: str, unlocked: set[str] | None = None) -> list[dict]:
    """Wardrobe cards for a character (male / female): hidden rarities left out, outfits
    that still have to be earned marked "locked" with their hint."""
    unlocked = unlocked or set()
    out = []
    for key, outfit in OUTFITS.items():
        if outfit["gender"] != avatar_style:
            continue
        if outfit["rarity"] in HIDDEN_RARITIES and key not in unlocked:
            continue
        locked = "unlock" in outfit and key not in unlocked
        out.append({"key": key, **outfit, "locked": locked,
                    "hint": UNLOCK_HINTS.get(outfit.get("unlock", ""), "")})
    return out


def background_available(key: str, owned: set[str] | None = None) -> bool:
    """Exists, and isn't a hidden rarity (HIDDEN_RARITIES applies to backgrounds too) —
    unless the user owns it (a mailbox gift)."""
    bg = BACKGROUNDS.get(key)
    if bg is None:
        return False
    return bg.get("rarity") not in HIDDEN_RARITIES or key in (owned or set())


def backgrounds_list(owned: set[str] | None = None) -> list[dict]:
    return [{"key": key, **bg} for key, bg in BACKGROUNDS.items() if background_available(key, owned)]
