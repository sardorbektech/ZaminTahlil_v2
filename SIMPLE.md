# SIMPLE.md — ZaminTahlil (focused version)

Instructions for AI coding agents. This is the **simplified scope** of ZaminTahlil. Everything here serves one goal: **get accurate, complete, timestamped data about a user-selected area** (rekognossirovka). Anything that does not serve that goal is out of scope (see §13). Read this whole file before writing code. If something is not covered, choose the simplest option and record it in `docs/DECISIONS.md`.

---

## 1. Goal

The user draws a rectangle or polygon on a 2D map and presses **"Rekognossirovka"**. The app:

1. Pulls satellite and weather data for that area from Google Earth Engine (GEE).
2. Computes terrain, vegetation, water, moisture, temperature and land-cover information from raw bands with plain, documented formula functions.
3. Tells what every part of the area is: swamp, water, trees, field, bare soil, road, built-up, bridge candidate, etc.
4. Shows how the area changed over the recent observation dates.
5. Shows past and forecast weather and its effect on the area.
6. Shows what data each satellite provided, and when.
7. Gives all numeric results to an LLM, which writes a Markdown report.

**Accuracy comes first.** Never fabricate, interpolate or guess a value and show it as measured. Every value has a source and an exact timestamp.

---

## 2. Language rules

| Item | Language |
|---|---|
| This file and `docs/*` | English |
| UI text, AI report | Uzbek (Latin; use `ʻ` U+02BB in oʻ/gʻ and `ʼ` U+02BC for tutuq belgisi) |
| Code comments and docstrings | Uzbek |
| Identifiers, DB columns, API paths, JSON keys | English |

All UI strings live in `frontend/js/i18n/uz.js`.

Time: store UTC epoch seconds (INTEGER). Display `DD.MM.YYYY HH:MM` in `Asia/Tashkent` (UTC+5). Use a single helper, `core/time.py::fmt_local(ts)`, with format `"%d.%m.%Y %H:%M"`.

---

## 3. Stack

**Backend:** Python 3.12.x, FastAPI, Uvicorn, Pydantic v2 + pydantic-settings, SQLAlchemy 2.x + aiosqlite (SQLite), earthengine-api, google-auth, numpy, scipy (`ndimage` only), Pillow, httpx, pytest, ruff.

**Frontend:** static HTML + CSS + vanilla JS ES modules, no build step. **Leaflet** with **Leaflet-Geoman** (or Leaflet.draw) for drawing, plus marked and DOMPurify for the report. Map: **one basemap, Esri World Imagery**. 2D only.

Do not add other dependencies without a clear need.

---

## 4. Principles

1. **API-first.** The backend exposes JSON under `/api/v1` with OpenAPI. A separate frontend will be built later, so the static frontend contains no business logic.
2. **One job at a time.** The backend returns `409` if a job is already running. The frontend locks every control except **Toʻxtatish** while a job runs.
3. **Always cancellable.** Cancelling frees memory and deletes partial files within ~2 seconds.
4. **Use precomputed products when they exist.** Examples: Landsat surface temperature, Sentinel-2 SCL, Cloud Score+, SMAP soil moisture, Sentinel-1 dB backscatter. Compute everything else with formula functions.
5. **Download only the bands in §5.**
6. **Replaceable analysis.** Each analysis step sits behind an `Analyzer` interface (§7.1), so it can later be swapped for an AI model.
7. **No silent gaps.** Missing data is shown as "maʼlumot yoʻq", never as zero or as an estimate.

---

## 5. Data sources

Verify every dataset ID and band name in the GEE catalog before use. Use the newest version of each, and never invent band names.

### 5.1 Satellites

| Source | GEE ID | Bands | Use |
|---|---|---|---|
| Sentinel-2 SR | `COPERNICUS/S2_SR_HARMONIZED` | B2, B3, B4, B5, B8, B8A, B11, B12, SCL | Main optical data: RGB, indices, land cover |
| Cloud Score+ | `GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED` | cs_cdf | Cloud masking |
| Sentinel-1 GRD | `COPERNICUS/S1_GRD` (IW mode) | VV, VH | Water, swamp, moisture, structures; works through clouds |
| Landsat 8 / 9 L2 | `LANDSAT/LC08/C02/T1_L2`, `LANDSAT/LC09/C02/T1_L2` | SR_B2–SR_B7, ST_B10, QA_PIXEL | Surface temperature; optical cross-check |
| SMAP L4 | `NASA/SMAP/SPL4SMGP/<latest>` | sm_surface, sm_rootzone | Soil moisture |
| Copernicus DEM | `COPERNICUS/DEM/GLO30` | DEM | Relief |

Scaling (verify in the catalog):

| Product | Conversion |
|---|---|
| Sentinel-2 SR | DN / 10000. Request as uint16. |
| Landsat SR | DN × 0.0000275 − 0.2 |
| Landsat ST_B10 | DN × 0.00341802 + 149.0 gives Kelvin; subtract 273.15 for °C |
| Sentinel-1 | Already in dB |

Scenes of the same sensor from the same day are mosaicked into one observation.

### 5.2 Weather

| Use | GEE ID |
|---|---|
| Past days, hourly | `ECMWF/ERA5_LAND/HOURLY`: temperature_2m, dewpoint_temperature_2m, total_precipitation_hourly, u/v wind 10m, volumetric_soil_water_layer_1 |
| Recent hours ERA5-Land doesn't cover yet (~5-day lag) | `NOAA/GFS0P25`, forecast hour 0 of each run |
| Forecast | `NOAA/GFS0P25`, latest run: temperature, relative humidity, precipitation (difference the accumulated values), wind, cloud cover |
| Daily rainfall | `UCSB-CHC/CHIRPS/V3/DAILY`: precipitation |

Every weather value is tagged with its source (`era5`, `gfs_analysis`, `gfs_forecast`, `chirps`) and timestamp.

---

## 6. Pipeline

`pipeline/recon.py` runs as an asyncio task. Progress is streamed over SSE, and cancellation is checked around every external call.

| # | Stage | Details |
|---|---|---|
| 1 | Validate AOI | Valid polygon, area ≤ `max_aoi_km2` (100). |
| 2 | Grid | EPSG:3857 (matches Leaflet exactly). Pixel size in projected units = `res_m / cos(lat_center)`; real ground size = `res_m`. Continuous data is resampled bilinearly; QA and class bands use nearest neighbour. |
| 3 | Scene discovery | Metadata only: scene IDs, acquisition times and cloud % within `lookback_days`. |
| 4 | Fingerprint | `sha256(normalized geometry + sorted scene IDs)`. If it matches an existing run, show that run and stop (toast: "Yangi sunʼiy yoʻldosh maʼlumoti yoʻq"). |
| 5 | Download | `computePixels` on the grid, chunked under GEE's size limit, running in parallel under the concurrency limit. |
| 6 | Weather | Area mean, min and max, hourly. |
| 7 | Analysis | §7. |
| 8 | Render | PNG layers that are transparent outside the AOI, plus `.npz` arrays kept for composites and pixel queries. |
| 9 | Persist | DB rows and `data/runs/{run_id}/`. |
| 10 | AI report | §8. If it fails, the run still succeeds. |

**Cancellation** (`POST /recon/{id}/cancel`): stop the task and HTTP calls, drop arrays and run `gc.collect()`, delete the run folder and DB rows, emit `cancelled`. The frontend then removes the run's overlays and unlocks the UI.

**Retention:** runs older than 24 hours are deleted on startup and every 10 minutes.

---

## 7. Analysis

Pure numpy functions only: no I/O, float32 arrays, NaN for invalid pixels. Each function's Uzbek docstring states its formula and the bands it uses.

### 7.1 Analyzer interface

```python
class Analyzer(Protocol):
    name: str          # masalan: "ndvi", "landcover"
    version: str       # masalan: "rules-1.0"
    def run(self, data: AnalyzerInput) -> AnalyzerOutput: ...  # qatlamlar, statistika, ishonchlilik
```

Analyzers are resolved from a registry by name, never imported directly by the pipeline.

### 7.2 Indices (S2 bands)

| Index | Formula | Bands |
|---|---|---|
| NDVI | (NIR−Red)/(NIR+Red) | B8, B4 |
| EVI | 2.5(NIR−Red)/(NIR+6Red−7.5Blue+1) | B8, B4, B2 |
| NDRE | (NIR−RE1)/(NIR+RE1) | B8A, B5 |
| NDWI | (Green−NIR)/(Green+NIR) | B3, B8 |
| MNDWI | (Green−SWIR1)/(Green+SWIR1) | B3, B11 |
| NDMI | (NIR−SWIR1)/(NIR+SWIR1) | B8, B11 |
| NBR | (NIR−SWIR2)/(NIR+SWIR2) | B8, B12 |
| NDBI | (SWIR1−NIR)/(SWIR1+NIR) | B11, B8 |
| BSI | ((SWIR1+Red)−(NIR+Blue))/((SWIR1+Red)+(NIR+Blue)) | B11, B4, B8, B2 |

Landsat equivalents are used for the cross-check in §7.6. Division by zero gives NaN.

### 7.3 Other products

- **SAR:** Lee 5×5 speckle filter; VV and VH in dB; VH−VV; RVI = 4·VH/(VV+VH) in linear units; water mask where VV < −15 dB (configurable constant).
- **Thermal:** Landsat LST in °C.
- **Terrain:** elevation; slope and aspect (Horn's method); hillshade; TRI; TPI; low areas and depressions.
- **RGB features (no computer vision):** brightness, chromaticity, excess green, local standard deviation (texture).
- **Soil moisture:** SMAP values and their trend.

### 7.4 Land-cover classification (rule-based)

| Code | UI label | Main evidence |
|---|---|---|
| 1 | Suv | MNDWI > 0.1 or NDWI > 0.2, low VV/VH |
| 2 | Botqoqlik | moderate NDWI/NDMI, NDVI 0.1–0.5, depression, low VV, high soil moisture |
| 3 | Daraxtzor | NDVI > 0.6, high texture, higher VH |
| 4 | Ekin / dala | NDVI 0.3–0.6, low texture |
| 5 | Siyrak oʻsimlik | NDVI 0.15–0.3 |
| 6 | Ochiq tuproq | BSI > 0, NDVI < 0.15 |
| 7 | Imorat | NDBI > 0, high VV, low NDVI |
| 8 | Yoʻl (ehtimoliy) | elongated connected components of built-up or bare pixels |
| 9 | Koʻprik (ehtimoliy) | road or built-up pixels crossing water |
| 10 | Kuygan hudud | low NBR plus a drop in NBR |
| 0 | Nomaʼlum / bulut | masked pixels |

All thresholds live in one constants module. Each pixel gets a confidence score, which is lowered when the result disagrees with S2 SCL.

### 7.5 Change and weather impact

- **Change:** ΔNDVI, ΔNDWI, ΔNDMI, ΔVV, Δsoil moisture and class transitions between consecutive real observations. Interpolated frames are not used.
- **Weather impact:** rule-based Uzbek statements with numbers and dates. Examples: rainfall versus moisture or backscatter change; temperature versus LST/NDVI; forecast waterlogging risk in low areas; frost; heat; strong wind.

### 7.6 Data quality (mandatory)

For every layer and date, store and show:

- valid pixel %
- cloud-masked %
- scene IDs
- acquisition time

Cross-check NDVI between Sentinel-2 and Landsat when both exist within 3 days, and report the difference. Any value based on less than 30% valid pixels is flagged "past ishonchlilik".

---

## 8. AI report

- **Providers:** `openrouter` (default; model `openrouter/free`), `openai`, `ollama`, all behind one interface.
- **History window:** default 10 messages. There is no chat UI.
- **Input:** numeric results only, as compact JSON: sources, scene times, class areas, statistics per date, terrain, changes, weather, quality flags. Keep an optional `images` field for later use; it stays unused now.
- **Prompt rules:** don't invent facts; cite dates as `DD.MM.YYYY HH:MM`; mark uncertain items.
- **Sections (Uzbek):** Umumiy maʼlumot · Relyef · Yer qoplami · Oʻzgarishlar · Ob-havo va taʼsiri · Prognoz va xavflar · Maʼlumot sifati va cheklovlar.
- **Once per fingerprint:** at most one report per fingerprint, i.e. a new report is allowed only when new satellite data arrives. A failed attempt may be retried.
- **Output:** Markdown, viewable in the panel and downloadable as `.md`.

---

## 9. GEE access and failover

- All GEE calls go through `gee/gateway.py`, run in threads.
- **Rate limiting:** semaphore (default 6) and backoff with jitter for 429, 503, "Too many concurrent aggregations" and timeouts.
- **Failover to the secondary GEE project** happens on quota or auth errors, exhausted retries, or a request exceeding `gee_request_timeout_s` (60).
  - `ee` holds global state, so switching re-initializes it under a lock once in-flight requests have drained.
  - The frontend shows the toast "Zaxira GEE loyihasiga oʻtildi".
- "User memory limit exceeded" does not trigger failover. Split the request into smaller tiles instead.

---

## 10. API usage log

- Every external call (GEE primary/secondary, AI providers) goes through `usage/tracker.py`.
- Calls are written to `data/logs/api_calls/YYYY-MM-DD.jsonl`, kept for 30 days, and never printed to the terminal.
- Each record has these fields: `ts`, `ts_local`, `run_id`, `service`, `operation`, `purpose`, `dataset`, `request` (summary), `status`, `duration_ms`, `bytes`, `retries`, `failover`, `response` (summary), `tokens_in`, `tokens_out`, `cost_usd`, `error`.
- `GET /api/v1/usage/runs/{id}` returns a Markdown summary: calls, time, bytes and failures per service and purpose, plus the call list. It is shown in the "Nazorat" tab.

---

## 11. Storage

- **SQLite settings:** WAL mode, foreign keys on, STRICT tables if supported.
- **Compact column types:**

  | Data | Type |
  |---|---|
  | IDs | INTEGER PK |
  | Times | INTEGER epoch |
  | Enums | small INTEGER (`IntEnum` in `db/enums.py`) |
  | Flags | 0/1 |
  | Values | REAL |
  | Hashes | 32-byte BLOB |
  | Rasters | files on disk (PNG + `.npz`); the DB stores only the path |

- **Tables:**

  | Table | Contents |
  |---|---|
  | `runs` | run record and fingerprint |
  | `scenes` | scene IDs, sensors, acquisition times, cloud % |
  | `layers` | layer kind, sensor, acquisition time, file path, min/max, valid %, quality flag |
  | `layer_stats` | per-layer statistics |
  | `class_areas` | class areas per date |
  | `weather` | weather values with source and time |
  | `reports` | AI reports (fingerprint unique) |
  | `settings` | single row |

- **Secrets** live in `.env`: two GEE projects with their key files, AI keys, and Ollama URL. The browser gets no secrets; the Esri basemap needs no key.

**Settings (defaults):**

| Setting | Default |
|---|---|
| `lookback_days` | 10 (1–60) |
| `weather_past_days` | 5 |
| `weather_forecast_days` | 5 |
| `max_scene_cloud_pct` | 40 |
| `cloud_score_threshold` | 0.60 |
| `s1_orbit_pass` | BOTH |
| `analysis_resolution_m` | 10 |
| `max_aoi_km2` | 100 |
| `gee_request_timeout_s` | 60 |
| `gee_max_retries` | 3 |
| `gee_max_concurrency` | 6 |
| `ai_provider` | openrouter |
| `ai_model` | openrouter/free |
| `ai_history_size` | 10 |

---

## 12. API and frontend

**Endpoints (`/api/v1`):**

| Endpoint | Purpose |
|---|---|
| `GET/PUT /settings` | read / update settings |
| `POST /recon` | start a run (`409` if one is active) |
| `GET /recon/active` | active run, if any |
| `GET /recon/{id}/events` | progress (SSE) |
| `POST /recon/{id}/cancel` | stop and clean up |
| `GET /recon/{id}` | run summary |
| `GET /recon/{id}/layers` | layer list; `/layers/{lid}.png` for images |
| `GET /recon/{id}/composite.png?date=&r=&g=&b=` | custom band composite |
| `GET /recon/{id}/pixel?lon=&lat=` | every value at a point, with time and source |
| `GET /recon/{id}/classes` | class areas |
| `GET /recon/{id}/changes` | change summary |
| `GET /recon/{id}/weather` | past, forecast and impact |
| `GET /recon/{id}/satellites` | what each satellite provided and when |
| `POST /recon/{id}/report`, `GET /recon/{id}/report` | generate / read the AI report |
| `GET /usage/runs/{id}` | usage summary (Markdown) |

Times in responses are given both as `*_ts` and `*_local`. Errors use the shape `{code, message_uz}`.

**Frontend:**

- **Single page, no scrolling anywhere** (`overflow: hidden`). Content fits through tabs and pagination.
- **Layout:**
  - Top bar: draw rectangle/polygon, clear, area in km², **Rekognossirovka**, **Toʻxtatish**, settings.
  - Center: Leaflet map with Esri World Imagery.
  - Right tabs: Qatlamlar · Maʼlumot · Ob-havo · Sunʼiy yoʻldoshlar · Hisobot · Nazorat.
  - Bottom: progress bar and a date slider over real observation dates, with a simple cross-fade between dates.
- **State machine:** `idle → ready → running → done | cancelled | error`. While running, everything is disabled except Toʻxtatish. State is restored after a page reload via `/recon/active`.
- **Scan animation:** during a run, an animated dashed outline and a moving sweep (CSS/SVG) over the AOI.
- **Layers:** `L.imageOverlay` per layer, with visibility, opacity, legend, timestamp and source. Several can be shown at once. A band composer offers true color, false color or custom R/G/B.
- **Map click:** a popup with all values at that point, each with its timestamp and source.
- **Cleanup:** on new run, cancel or clear, remove the overlays and revoke object URLs.

---

## 13. Out of scope (do not build)

- 3D globe and 3D terrain (Cesium)
- Google basemaps or any second basemap
- Live satellite position and orbit tracking
- Interpolated or "smoothed" synthetic frames
- PDF/DOCX export
- AI chat, AI image input
- Extra derived indices beyond §7 (e.g. trafficability), extra satellites (MODIS, VIIRS, Sentinel-3, Proba-V, HLS, ASTER, PALSAR)

---

## 14. Standards, tests, commands

- **Python style:** type hints and ruff. No `print`; logs go to files under `data/logs/app/` only. Uvicorn runs with `--no-access-log`.
- **No hard-coding inside functions:** dataset IDs go in `gee/datasets/`, thresholds in constants modules.
- **Tests (no network, fake GEE gateway):**
  - every formula and rule (including NaN and zero-division)
  - fingerprint dedupe and the report-once rule
  - cancellation cleanup
  - failover on simulated timeout or 429
  - 24 h cleanup
  - time formatting
  - JSONL schema
  - quality flags
- **Setup and commands:**

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn backend.app.main:app --reload --no-access-log
pytest -q && ruff check .
```

**Build order:**

1. Skeleton, settings, logging, DB, map, drawing, state machine, SSE, cancellation.
2. GEE gateway with failover, scene discovery, fingerprint.
3. Downloads, indices, SAR, LST, terrain, layers, pixel popup.
4. Classification, change detection, quality checks, date slider.
5. Weather and weather impact.
6. AI report.
7. Usage panel and cleanup.

**Done means:**

- tests pass
- every external call is logged
- every displayed value has a time and source
- UI text is Uzbek
- no page scroll
- cancellation frees everything
