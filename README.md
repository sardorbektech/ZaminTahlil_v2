# ZaminTahlil v2 — Hudud Rekognossirovkasi Tizimi

ZaminTahlil — foydalanuvchi xaritada tanlagan hudud (to'g'ri to'rtburchak yoki ko'pburchak, ≤ 100 km²) uchun Google Earth Engine (GEE) orqali sun'iy yo'ldosh (Sentinel-2, Sentinel-1, Landsat 8/9, SMAP, Copernicus DEM) va ob-havo (ERA5-Land, GFS, CHIRPS) ma'lumotlarini yuklovchi, sof matematik formulalar yordamida qatlamlarni tahlil qiluvchi, yer qoplamini klassifikatsiya qiluvchi va LLM yordamida batafsil tahliliy hisobot tuzuvchi dasturiy majmua.

---

## 1. Talablar

- **Python:** 3.12.x
- **Operatsion tizim:** Windows / Linux / macOS
- **Internet ulanishi:** GEE va AI xizmatlari bilan ishlash uchun

---

## 2. Muhitni Sozlash

1. Virtual muhitni yaratish va faollashtirish:
   ```bash
   python -m venv .venv
   # Windows (PowerShell):
   .venv\Scripts\Activate.ps1
   # Linux / macOS:
   source .venv/bin/activate
   ```

2. Paketlarni o'rnatish:
   ```bash
   pip install -r requirements-dev.txt
   ```

3. Muhit konfiguratsiyasini (.env) yaratish:
   ```bash
   cp .env.example .env
   ```
   `.env` fayliga GEE loyihalari, xizmat hisobi kalit fayllari (`secrets/` papkasida, git'ga kirmaydi)
   va AI API kalitlarini kiriting. `.env` va `secrets/` hech qachon commit qilinmaydi.

---

## 3. Ishga Tushirish

Serverni ishga tushirish:
```bash
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --no-access-log
```
Ilova brauzerda ochiladi: `http://localhost:8000`
API hujjatlari (Swagger): `http://localhost:8000/docs`

---

## 4. Testlarni Ishga Tushirish

Barcha unit va integratsiya testlarini tekshirish:
```bash
.venv\Scripts\python.exe -m pytest -q
```

Linter va format tekshiruvi:
```bash
.venv\Scripts\python.exe -m ruff check .
```

---

## 5. Loyiha Tuzilishi

- `backend/app/main.py` — FastAPI ilovasi va marshrutizatsiya
- `backend/app/core/` — Konfiguratsiya, konstantalar, xatoliklar va vaqt boshqaruvi
- `backend/app/db/` — SQLite WAL modellari va ma'lumotlar bazasi sessiyalari
- `backend/app/gee/` — GEE Gateway, failover va datasetlar
- `backend/app/analysis/` — Indekslar, SAR, LST, relyef, yer qoplami klassifikatsiyasi va o'zgarishlar
- `backend/app/weather/` — Ob-havo agregatsiyasi va ta'sirini baholash
- `backend/app/pipeline/` — 10 bosqichli async rekognossirovka quvuri va SSE
- `backend/app/ai/` — OpenRouter/OpenAI/Ollama orqali Markdown hisobot generatori
- `backend/app/usage/` — API chaqiruvlari hisobi va nazorati (JSONL)
- `frontend/` — Leaflet asosidagi statik interfeys (HTML/CSS/JS)
- `tests/` — Tarmoqsiz testlar (soxta GEE manbasi `tests/fakes.py`)
- `docs/DECISIONS.md` — SIMPLE.md da yozilmagan texnik qarorlar

---

## 6. Asosiy imkoniyatlar

- **Kirish:** username + parol (roʻyxatdan oʻtish yoʻq — username boʻlmasa yangisi yaratiladi). Har kim faqat oʻz maydonlarini koʻradi.
- **Maydonlarim:** tahlil qilingan maydonlar ID va nom bilan saqlanadi; istalgan vaqtda qayta ochish, nomlash, oʻchirish mumkin.
- **2D / 3D:** Leaflet xaritasi yoki Three.js 3D relyef (Copernicus DEM) — ikkalasida ham yer qoplami ranglari, nomlari va istalgan qatlamlar.
- **Kuzatuv sanasi:** slayder haqiqiy sanalar orasida qatlamlarni silliq almashtiradi.
- **Chat:** AI (standart: OpenAI `gpt-6-luna`) faqat tanlangan maydon haqidagi savollarga javob beradi.
- **ML/CV:** qatlamlar uchun klassik ML va computer vision modellarini ulash nuqtasi — `backend/app/analysis/models/`.
- Texnik tavsif: `ABOUT.md`; agentlar uchun qoidalar: `AGENTS.md`; qarorlar: `docs/DECISIONS.md`.
