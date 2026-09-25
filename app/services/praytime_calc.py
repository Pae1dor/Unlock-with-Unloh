"""Offline prayer-time calculation, used only when the Aladhan API is unreachable.

Same settings as our Aladhan request (method 3, Muslim World League): Fajr at 18° and
Isha at 17° below the horizon, Asr by the Shafi'i shadow rule (school 0, Aladhan's
default), Maghrib at sunset. The astronomy follows the well-known PrayTimes.org
algorithm; results normally land within a minute or two of Aladhan's.
"""
from __future__ import annotations

import math
import re
from datetime import date

FAJR_ANGLE = 18.0
ISHA_ANGLE = 17.0
ASR_SHADOW_FACTOR = 1      # Shafi'i
SUN_HORIZON = 0.833        # refraction + solar radius
THAILAND_UTC_OFFSET = 7.0

# Thailand's 77 provinces (city centre), plus a few common alternative names.
# name -> (latitude, longitude, English aliases...)
_PROVINCES: dict[str, tuple] = {
    "กรุงเทพมหานคร": (13.7563, 100.5018, "bangkok", "กรุงเทพ", "กรุงเทพฯ", "กทม"),
    "กระบี่": (8.0863, 98.9063, "krabi"),
    "กาญจนบุรี": (14.0228, 99.5328, "kanchanaburi"),
    "กาฬสินธุ์": (16.4322, 103.5061, "kalasin"),
    "กำแพงเพชร": (16.4828, 99.5227, "kamphaeng phet"),
    "ขอนแก่น": (16.4419, 102.8360, "khon kaen"),
    "จันทบุรี": (12.6114, 102.1039, "chanthaburi"),
    "ฉะเชิงเทรา": (13.6904, 101.0779, "chachoengsao"),
    "ชลบุรี": (13.3611, 100.9847, "chonburi", "chon buri"),
    "ชัยนาท": (15.1851, 100.1251, "chai nat", "chainat"),
    "ชัยภูมิ": (15.8068, 102.0317, "chaiyaphum"),
    "ชุมพร": (10.4930, 99.1800, "chumphon"),
    "เชียงราย": (19.9105, 99.8406, "chiang rai"),
    "เชียงใหม่": (18.7883, 98.9853, "chiang mai"),
    "ตรัง": (7.5563, 99.6114, "trang"),
    "ตราด": (12.2428, 102.5175, "trat"),
    "ตาก": (16.8840, 99.1259, "tak"),
    "นครนายก": (14.2069, 101.2131, "nakhon nayok"),
    "นครปฐม": (13.8199, 100.0622, "nakhon pathom"),
    "นครพนม": (17.3920, 104.7695, "nakhon phanom"),
    "นครราชสีมา": (14.9799, 102.0978, "nakhon ratchasima", "korat", "โคราช"),
    "นครศรีธรรมราช": (8.4304, 99.9631, "nakhon si thammarat"),
    "นครสวรรค์": (15.7047, 100.1372, "nakhon sawan"),
    "นนทบุรี": (13.8591, 100.5217, "nonthaburi"),
    "นราธิวาส": (6.4255, 101.8253, "narathiwat"),
    "น่าน": (18.7756, 100.7730, "nan"),
    "บึงกาฬ": (18.3609, 103.6466, "bueng kan", "buengkan"),
    "บุรีรัมย์": (14.9930, 103.1029, "buriram", "buri ram"),
    "ปทุมธานี": (14.0208, 100.5250, "pathum thani"),
    "ประจวบคีรีขันธ์": (11.8124, 99.7973, "prachuap khiri khan"),
    "ปราจีนบุรี": (14.0509, 101.3717, "prachinburi", "prachin buri"),
    "ปัตตานี": (6.8696, 101.2501, "pattani"),
    "พระนครศรีอยุธยา": (14.3532, 100.5689, "ayutthaya", "phra nakhon si ayutthaya", "อยุธยา"),
    "พะเยา": (19.1666, 99.9019, "phayao"),
    "พังงา": (8.4509, 98.5255, "phang nga", "phangnga"),
    "พัทลุง": (7.6167, 100.0740, "phatthalung"),
    "พิจิตร": (16.4429, 100.3487, "phichit"),
    "พิษณุโลก": (16.8211, 100.2659, "phitsanulok"),
    "เพชรบุรี": (13.1112, 99.9391, "phetchaburi"),
    "เพชรบูรณ์": (16.4190, 101.1591, "phetchabun"),
    "แพร่": (18.1445, 100.1403, "phrae"),
    "ภูเก็ต": (7.8804, 98.3923, "phuket"),
    "มหาสารคาม": (16.1851, 103.3028, "maha sarakham"),
    "มุกดาหาร": (16.5453, 104.7235, "mukdahan"),
    "แม่ฮ่องสอน": (19.3020, 97.9654, "mae hong son"),
    "ยโสธร": (15.7921, 104.1453, "yasothon"),
    "ยะลา": (6.5411, 101.2804, "yala"),
    "ร้อยเอ็ด": (16.0538, 103.6520, "roi et"),
    "ระนอง": (9.9529, 98.6085, "ranong"),
    "ระยอง": (12.6814, 101.2816, "rayong"),
    "ราชบุรี": (13.5283, 99.8134, "ratchaburi"),
    "ลพบุรี": (14.7995, 100.6534, "lopburi", "lop buri"),
    "ลำปาง": (18.2888, 99.4909, "lampang"),
    "ลำพูน": (18.5745, 99.0087, "lamphun"),
    "เลย": (17.4860, 101.7223, "loei"),
    "ศรีสะเกษ": (15.1186, 104.3220, "si sa ket", "sisaket"),
    "สกลนคร": (17.1545, 104.1348, "sakon nakhon"),
    "สงขลา": (7.1898, 100.5954, "songkhla"),
    "หาดใหญ่": (7.0084, 100.4767, "hat yai", "hatyai"),
    "สตูล": (6.6238, 100.0674, "satun"),
    "สมุทรปราการ": (13.5991, 100.5998, "samut prakan"),
    "สมุทรสงคราม": (13.4098, 100.0023, "samut songkhram"),
    "สมุทรสาคร": (13.5475, 100.2744, "samut sakhon"),
    "สระแก้ว": (13.8240, 102.0646, "sa kaeo"),
    "สระบุรี": (14.5289, 100.9101, "saraburi"),
    "สิงห์บุรี": (14.8936, 100.3967, "sing buri", "singburi"),
    "สุโขทัย": (17.0056, 99.8264, "sukhothai"),
    "สุพรรณบุรี": (14.4745, 100.1177, "suphan buri", "suphanburi"),
    "สุราษฎร์ธานี": (9.1382, 99.3217, "surat thani"),
    "สุรินทร์": (14.8818, 103.4936, "surin"),
    "หนองคาย": (17.8783, 102.7420, "nong khai"),
    "หนองบัวลำภู": (17.2218, 102.4260, "nong bua lam phu"),
    "อ่างทอง": (14.5896, 100.4550, "ang thong"),
    "อำนาจเจริญ": (15.8657, 104.6258, "amnat charoen"),
    "อุดรธานี": (17.4138, 102.7870, "udon thani"),
    "อุตรดิตถ์": (17.6200, 100.0993, "uttaradit"),
    "อุทัยธานี": (15.3835, 100.0246, "uthai thani"),
    "อุบลราชธานี": (15.2287, 104.8564, "ubon ratchathani", "ubon"),
}


def _normalize(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"^(จังหวัด|จ\.)\s*", "", s)
    s = re.sub(r"\s*(province|city)$", "", s)
    return re.sub(r"[\s\-_.ฯ]", "", s)


_LOOKUP: dict[str, tuple[float, float]] = {}
for _name, (_lat, _lng, *_aliases) in _PROVINCES.items():
    for _n in (_name, *_aliases):
        _LOOKUP[_normalize(_n)] = (_lat, _lng)


def coordinates_for(city: str) -> tuple[float, float] | None:
    return _LOOKUP.get(_normalize(city))


# ---- astronomy (degrees in, degrees out) ----
def _sin(d): return math.sin(math.radians(d))
def _cos(d): return math.cos(math.radians(d))
def _tan(d): return math.tan(math.radians(d))
def _arcsin(x): return math.degrees(math.asin(x))
def _arccos(x): return math.degrees(math.acos(x))
def _arctan2(y, x): return math.degrees(math.atan2(y, x))
def _arccot(x): return math.degrees(math.atan(1 / x))
def _fix(a, b): return a - b * math.floor(a / b)


def _julian(d: date) -> float:
    y, m = d.year, d.month
    if m <= 2:
        y -= 1
        m += 12
    a = math.floor(y / 100)
    b = 2 - a + math.floor(a / 4)
    return math.floor(365.25 * (y + 4716)) + math.floor(30.6001 * (m + 1)) + d.day + b - 1524.5


def _sun(jd: float) -> tuple[float, float]:
    """(declination, equation of time in hours)."""
    D = jd - 2451545.0
    g = _fix(357.529 + 0.98560028 * D, 360)
    q = _fix(280.459 + 0.98564736 * D, 360)
    L = _fix(q + 1.915 * _sin(g) + 0.020 * _sin(2 * g), 360)
    e = 23.439 - 0.00000036 * D
    ra = _fix(_arctan2(_cos(e) * _sin(L), _cos(L)) / 15, 24)
    return _arcsin(_sin(e) * _sin(L)), q / 15 - ra


def calculate(lat: float, lng: float, day: date, utc_offset: float = THAILAND_UTC_OFFSET) -> dict[str, str]:
    """Return {'Fajr': 'HH:MM', 'Sunrise': ..., 'Dhuhr': ..., 'Asr': ..., 'Maghrib': ..., 'Isha': ...}."""
    jd = _julian(day) - lng / (15 * 24)

    def midday(t):
        return _fix(12 - _sun(jd + t)[1], 24)

    def angle_time(angle, t, before_noon=False):
        decl = _sun(jd + t)[0]
        x = (-_sin(angle) - _sin(decl) * _sin(lat)) / (_cos(decl) * _cos(lat))
        span = _arccos(max(-1.0, min(1.0, x))) / 15
        return midday(t) + (-span if before_noon else span)

    def asr(t):
        decl = _sun(jd + t)[0]
        return angle_time(-_arccot(ASR_SHADOW_FACTOR + _tan(abs(lat - decl))), t)

    # Start from rough guesses (hours) and refine: each time depends on the sun's position at that time.
    t = {"Fajr": 5, "Sunrise": 6, "Dhuhr": 12, "Asr": 13, "Maghrib": 18, "Isha": 18}
    for _ in range(2):
        f = {k: v / 24 for k, v in t.items()}
        t = {
            "Fajr": angle_time(FAJR_ANGLE, f["Fajr"], before_noon=True),
            "Sunrise": angle_time(SUN_HORIZON, f["Sunrise"], before_noon=True),
            "Dhuhr": midday(f["Dhuhr"]),
            "Asr": asr(f["Asr"]),
            "Maghrib": angle_time(SUN_HORIZON, f["Maghrib"]),
            "Isha": angle_time(ISHA_ANGLE, f["Isha"]),
        }

    out = {}
    for key, hours in t.items():
        local = _fix(hours + utc_offset - lng / 15, 24)
        minutes = int(math.floor(local * 60 + 0.5))   # round to the nearest minute
        out[key] = f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"
    return out
