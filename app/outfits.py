"""Character outfits (ชุดตัวละคร).

Each outfit is one full-body picture of the character already wearing it — like the
pre-rendered player cards in a football game — so switching outfits is just switching
images. Every image should share the same pose, canvas size and transparent background.

This is a test catalog kept in code; new outfits = drop an image in static/img and add a row.
"""

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

RARITY_LABELS = {
    "common": "ทั่วไป",
    "limited": "ลิมิเต็ด",
}


def outfits_for(avatar_style: str) -> list[dict]:
    """Outfits that fit a character (male / female); each dict also carries its key."""
    return [
        {"key": key, **outfit}
        for key, outfit in OUTFITS.items()
        if outfit["gender"] == avatar_style
    ]


def backgrounds_list() -> list[dict]:
    return [{"key": key, **bg} for key, bg in BACKGROUNDS.items()]
