# ประชาชนเพื่อพี่น้องอิสลาม (Prachachon Puea Peenong Islam)

แอปพลิเคชันชุมชนมุสลิมไทย — a Thai Muslim community app built as a **server-rendered
FastAPI site styled as a mobile phone screen** (centred 430px frame, green/off-white
Islamic theme, bottom tab bar).

No build step, no npm, no framework. Just `pip install`, `uvicorn`, and a browser.

---

## Features

| Screen | Route | Notes |
| --- | --- | --- |
| หน้าแรก | `/` | Greeting, Gregorian + Hijri date, city, 5-prayer strip, 8 quick actions |
| เวลาละหมาด | `/prayer-times` | Live prayer times, next-prayer highlight, city selector, notification toggle |
| อัลกุรอาน | `/quran`, `/quran/{1-114}` | 114 surahs with client-side search; Arabic (Uthmani) + Thai translation + per-ayah audio |
| บริจาค | `/donation`, `/donation/{slug}`, `/donation/history` | Campaigns with **real generated QR codes**, self-reported transfers |
| ค้นหามัสยิด | `/mosques` | Leaflet + OpenStreetMap, geolocation distance sorting |
| ข่าวสาร | `/news`, `/news/{id}` | Category tabs (ทั้งหมด / บทความ / กิจกรรม / ประกาศ) |
| ชุมชน | `/community`, `/community/new`, `/community/{id}` | Forum with AJAX likes and comments |
| บัญชี | `/profile` | Edit name / city / phone, donation history, logout |
| Auth | `/register`, `/login`, `/logout` | Email + password, bcrypt, JWT in an httpOnly cookie |

JSON endpoints used by the front-end JS: `/api/mosques`, `/api/prayer-notifications`,
`/api/community/{id}/like`, `/api/community/{id}/comments`.

---

## Quick start (SQLite — zero dependencies, no Docker)

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # macOS / Linux

pip install -r requirements.txt

cp .env.example .env            # then set DATABASE_URL=sqlite:///./dev.db
python -m app.seed              # seeds news, mosques, campaigns + generates QR PNGs
uvicorn app.main:app --reload
```

Open <http://127.0.0.1:8000>.

## Running against PostgreSQL

```bash
docker-compose up -d db         # postgres:16, db "islamapp", password "postgres"
# .env -> DATABASE_URL=postgresql://postgres:postgres@localhost:5432/islamapp
python -m app.seed
uvicorn app.main:app --reload
```

Tables are created automatically on startup via `Base.metadata.create_all()` — there are
no Alembic migrations. Only portable column types are used, so **SQLite and PostgreSQL
are interchangeable** via `DATABASE_URL`.

### Environment variables

| Variable | Default | Purpose |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./dev.db` | SQLAlchemy connection string |
| `SECRET_KEY` | dev placeholder | **Change in production** — signs the JWT |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `10080` (7 days) | Cookie / token lifetime |
| `DEFAULT_CITY` | `กรุงเทพมหานคร` | Fallback city for prayer times |

---

## External APIs

Both are free and need no API key. Responses are cached in-process (prayer times per
city+date, the surah list, and each fetched surah), and every call sets
`follow_redirects=True` — **Aladhan answers `timingsByCity` with a 302**, so without it
the response body is empty.

| Service | Endpoint | Used for |
| --- | --- | --- |
| Aladhan | `https://api.aladhan.com/v1/timingsByCity` (method 3, Muslim World League) | 5 prayer times + Hijri date |
| alquran.cloud | `https://api.alquran.cloud/v1/surah` | 114-surah list |
| alquran.cloud | `.../v1/surah/{n}/editions/quran-uthmani,th.thai,ar.alafasy` | Arabic text, Thai translation, per-ayah audio |

**Thai edition slug: `th.thai`** (King Fahad Quran Complex) — confirmed by calling
`GET /v1/edition?language=th`, which returns exactly one Thai translation.
Audio comes from `ar.alafasy` (Mishary Alafasy) as per-ayah `.mp3` URLs.

City names work in **both Thai and English** (`ปัตตานี` and `Pattani` both resolve).

If either API is unreachable the affected page shows a friendly Thai message instead of a
stack trace; every non-API page (news, mosques, donation, community, auth) keeps working
fully offline.

---

## Notes

- **Auth is email + password only.** Google/Facebook OAuth was deliberately deferred and
  is not stubbed anywhere in the UI.
- **Donations are self-reported.** There is no payment gateway; the QR codes are real,
  scannable PNGs generated at seed time into `static/qr/`, encoding a plaintext
  PromptPay-style placeholder plus the org's bank details.
- **News images are CSS colour blocks**, not hotlinked images — the UI has no external
  dependency other than Leaflet (from cdnjs) on the mosque page.
- `python -m app.seed` is **idempotent** — re-running it skips existing rows and only
  refreshes the QR PNGs on disk.

## Project layout

```
app/
  main.py database.py models.py schemas.py auth.py deps.py config.py templating.py seed.py
  routers/   auth home prayer quran mosques news community donation profile
  services/  aladhan.py alquran.py
static/  css/style.css  js/{map,forum,prayer,quran-search}.js  qr/ (generated)
templates/  base.html _icons.html + one per page
```
