# ZaminTahlil v2 — Loyiha Qoidalari (`.agents/rules/project.md`)

## 1. Stek va Muhit
- **Backend:** Python 3.12, FastAPI, SQLAlchemy 2 (async SQLite WAL), Pydantic v2 + pydantic-settings, earthengine-api, google-auth, numpy, scipy (`ndimage`), Pillow, httpx.
- **Frontend:** Vanilla HTML/CSS/JS (ES modules, no build), Leaflet + Esri World Imagery, Marked, DOMPurify. Yagona sahifa (`overflow: hidden`).
- **Ishga tushirish:** `.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload`
- **Test:** `.venv\Scripts\python.exe -m pytest -q`
- **Lint:** `.venv\Scripts\python.exe -m ruff check .`

## 2. Loyihaga Xos Me'yorlar
- **Foydalanuvchi talabi (Terminal log):** Har bir sun'iy yo'ldosh va ob-havo ma'lumotlari qabul qilinganda va qayta ishlanganda terminalda qaysi sensor, qaysi sana/vaqt, qaysi bandlar kelayotgani aniq, chiroyli formatda chop etilishi shart.
- **Til qoidalari:** UI matnlari va AI hisobot — O'zbek lotin alifbosida (`oʻ`, `gʻ`, `ʼ`). Kod docstringlari — O'zbek tilida. O'zgaruvchilar, DB ustunlari, API — Ingliz tilida.
- **Vaqt formati:** Barcha vaqtlar UTC epoch INTEGER sifatida saqlanadi. UI da `Asia/Tashkent` (UTC+5) bo'yicha `DD.MM.YYYY HH:MM` formatida (`core/time.py::fmt_local(ts)`).
- **Aniqlik va soxta ma'lumot taqiqi:** Hech qanday taxminiy/soxta qiymatlar ko'rsatilmaydi. Ma'lumot yo'q bo'lsa "maʼlumot yoʻq" deb ko'rsatiladi.
- **Bitta vazifa:** Bir vaqtning o'zida faqat bitta rekognossirovka bajariladi (band bo'lsa `409 Conflict`).
- **Bekor qilish:** `POST /recon/{id}/cancel` 2 soniyada resurslarni bo'shatadi, vaqtinchalik fayllarni o'chiradi.
- **GEE Failover:** Asosiy GEE xatolik bersa (quota, 429, timeout > 60s), zaxira GEE loyihasiga avtomatik o'tiladi.
