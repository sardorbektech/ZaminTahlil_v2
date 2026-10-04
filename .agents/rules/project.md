# ZaminTahlil v2 — Loyiha qoidalari

Toʻliq va yagona manba: **`AGENTS.md`** (ildiz papkada). Talablar — `SIMPLE.md`, texnik tavsif — `ABOUT.md`,
qarorlar — `docs/DECISIONS.md`.

Qisqacha:
- **Ishga tushirish:** `.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --no-access-log`
- **Test:** `.venv\Scripts\python.exe -m pytest -q`
- **Lint:** `.venv\Scripts\python.exe -m ruff check .`
- **Terminal log:** standart holatda oʻchiq (loglar `data/logs/app/` da); `.env` da `LOG_TO_CONSOLE=true` boʻlsa, har bir
  sensor, sana va band qabul qilinishi terminalga ham chiqadi (docs/DECISIONS.md, 1-qaror).
- Soxta/taxminiy qiymat koʻrsatilmaydi — maʼlumot yoʻq boʻlsa «maʼlumot yoʻq».
- Kirish: username + parol (token yoʻq); har kim faqat oʻz maydonlarini koʻradi; saqlangan maydonlar faqat egasi oʻchirganda oʻchadi.
