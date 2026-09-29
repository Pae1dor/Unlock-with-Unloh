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
}

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
