# ABOUT.md — Technical description of ZaminTahlil v2

ZaminTahlil performs a reconnaissance (*rekognossirovka*) of a user-drawn area (rectangle or polygon, ≤ 100 km²).
It pulls satellite and weather data from Google Earth Engine (GEE), computes every derived value with documented
NumPy formulas, classifies land cover, tracks changes between real observation dates, evaluates weather impact,
and lets an LLM write an Uzbek Markdown report and answer questions about the area. Every number carries its
source dataset and exact acquisition time; missing data is reported as "maʼlumot yoʻq", never as zero or as an estimate.

The requirements are in `SIMPLE.md`; decisions not covered there are in `docs/DECISIONS.md`.

---

## 1. Stack

| Part | Technology |
|---|---|
| API | Python 3.12, FastAPI (JSON under `/api/v1`, OpenAPI at `/docs`), Uvicorn (`--no-access-log`) |
| Data | SQLAlchemy 2 + aiosqlite (SQLite, WAL, foreign keys, STRICT tables, versioned migrations) |
| GEE | `earthengine-api` + `google-auth` service accounts (primary and secondary project) |
| Numerics | NumPy, SciPy (`ndimage` only), Pillow |
| AI | HTTPX → OpenAI (default model `gpt-6-luna`), OpenRouter or Ollama behind one interface |
| UI | Static HTML/CSS/ES modules (no build): Leaflet + Leaflet-Geoman (2D), Three.js r160 (3D), marked + DOMPurify. The page never scrolls; panel content scrolls internally |

## 2. Users and saved areas

- **Login without tokens.** The browser sends `Authorization: Basic base64(username:password)` (UTF-8) with every request.
  `POST /api/v1/auth/login` creates the user if the username does not exist (1–64 characters, password ≥ 1 character)
  or verifies the password otherwise (401 on mismatch). Every other endpoint only verifies and never creates users.
- **Password storage:** PBKDF2-HMAC-SHA256, 200 000 iterations, 16-byte random salt, 32-byte hash (`users` table).
  Verified derivations are cached in memory keyed by *(salt, sha256(password), iterations)*, so a recreated database
  can never match a stale cache entry.
- **Ownership:** every run belongs to a user (`runs.user_id`). Other users get 404 for it. The fingerprint includes the user,
  so de-duplication and the "one report per fingerprint" rule are per user.
- **Saved areas:** completed runs are kept until the owner deletes them (`DELETE /recon/{id}`). `GET /recon` lists them,
  `PATCH /recon/{id}` renames them. Failed runs are purged after 24 h.
- **Deleting the database file is safe.** At startup a missing DB is recreated from scratch (stale `-wal/-shm` files are
  removed first). Run folders without a DB row are deleted. Completed runs whose `summary.json` is gone are dropped.
  The `runs` ID sequence is seeded from the highest `run_id` in the usage logs, so log entries never collide with new runs.
  The frontend keeps the credentials in `sessionStorage` and re-sends `/auth/login` once after a 401, which transparently
  recreates the user.

---

## 3. What happens after "Rekognossirovka" is pressed

The frontend sends `POST /api/v1/recon` with `{aoi: GeoJSON Polygon, name}`. The request returns immediately with
`run_id`. The pipeline (`backend/app/pipeline/recon.py`) runs as one asyncio task, and progress is streamed over SSE
(`GET /recon/{id}/events`; the frontend reads it with `fetch` because the auth header is needed). Each event has
`type` (`progress`, `failover`, `warning`, `duplicate`, `done`, `cancelled`, `error`), `stage`, overall `progress`
(stage weights 1/1/4/1/40/8/25/10/4/6 %), an Uzbek message and `ts`/`ts_local`.

### Stage 0 — Request checks (`api/routes_recon.py`)

1. Basic auth → user. If any job is running on the server → **409** (one job at a time).
2. A **snapshot** of the settings row is taken (`RunSettings`); it is stored in `runs.settings_json` and used for the whole run.
3. The configured land-cover analyzer (`landcover_analyzer`, default `landcover`) must exist in the analyzer registry.
4. **AOI validation** (`pipeline/grid.py`): a Feature is unwrapped to its Polygon. Rings are closed. Every coordinate must be
   finite with lon ∈ [−180, 180] and lat ∈ [−85, 85]. A ring needs ≥ 3 distinct points. Self-intersection is checked with an
   O(n²) segment-orientation test.
5. **Area** on the sphere (R = 6 378 137 m): `A = |Σ (λᵢ₊₁ − λᵢ)(2 + sin φᵢ + sin φᵢ₊₁)| · R² / 2` for the outer ring, minus the holes.
   It must be ≤ `max_aoi_km2` (100). Otherwise → 422 `INVALID_AOI`.
6. GEE must be configured (`GEE_PROJECT_*` + existing key file); otherwise → `GEE_NOT_CONFIGURED`.
7. A `runs` row is inserted with status RUNNING, owner and name (default `Maydon DD.MM.YYYY HH:MM`), and the task starts.

### Stage 1–2 — Grid (`build_grid`, `rasterize_aoi`)

- Projection **EPSG:3857** (same as Leaflet). Projected pixel size `p = res_m / cos(φ_center)`; ground size ≈ `res_m` (10 m).
- The grid origin is snapped to multiples of `p` (`min_x = ⌊min_x/p⌋·p`, `max_y = ⌈max_y/p⌉·p`), so the same AOI always gives
  the same grid. `W = ⌈(max_x − min_x)/p⌉` and `H = ⌈(max_y − min_y)/p⌉`, with at most 16 M pixels.
- The AOI is rasterised with Pillow (`True` inside, holes excluded).
- True ground area of a pixel in row *r*: `(p · cos φ_r)²`. This is used for every hectare figure.
- The grid (origin, `p`, size, lat/lon bounds) is saved in `runs.grid_json`.

### Stage 3 — Scene discovery (metadata only)

Six `getInfo` requests run in parallel through the gateway (`gee/sources.py::discover`). The time window is `[now − lookback_days, now]` (default 10 days).

| Request | Earth Engine expression | Returned properties |
|---|---|---|
| Sentinel-2 | `ImageCollection("COPERNICUS/S2_SR_HARMONIZED").filterBounds(aoi).filterDate(t0,t1).filter(CLOUDY_PIXEL_PERCENTAGE ≤ max_scene_cloud_pct).limit(500)` mapped to Features | `system:index`, `system:time_start`, `CLOUDY_PIXEL_PERCENTAGE`, `SPACECRAFT_NAME` |
| Sentinel-1 | `COPERNICUS/S1_GRD` + `instrumentMode = IW` + polarisations contain VV and VH (+ `orbitProperties_pass` if not BOTH) | index, time, orbit pass, platform |
| Landsat 8, Landsat 9 | `LANDSAT/LC08/C02/T1_L2`, `LANDSAT/LC09/C02/T1_L2` + `CLOUD_COVER ≤ max` | index, time, `CLOUD_COVER`, `SPACECRAFT_ID` |
| Copernicus DEM | `COPERNICUS/DEM/GLO30_2024_1.filterBounds(aoi)` → tile ids, min/max `system:time_start` | tiles are then limited to the 1° cells named in their ids (some catalog tiles have broken footprints) |
| SMAP L4 | `NASA/SMAP/SPL4SMGP/008` in the window, newest image | id, time |

Scenes of the same sensor on the same UTC day form one **observation** (they will be mosaicked). The observation time is the earliest scene time.

### Stage 4 — Fingerprint and de-duplication

`fingerprint = SHA-256( JSON{ coordinates rounded to 6 decimals, sorted ["<dataset>/<scene_id>", …, "__user__:<id>"] } )` (32 bytes).
If the same user already has a completed run with this fingerprint, nothing new arrived from the satellites. The new run row
and folder are deleted, and the `duplicate` event carries `existing_run_id`. The frontend then opens that run and shows
"Yangi sunʼiy yoʻldosh maʼlumoti yoʻq". DEM and SMAP are not part of the fingerprint (SMAP changes every 3 h).

### Stage 5 — Download (`computePixels`)

Items are downloaded one after another (DEM, SMAP, then every observation). Each item is split into **512 × 512** tiles,
which are fetched in parallel under the gateway semaphore (6). Request per tile:

```json
{ "expression": <ee.Image>, "fileFormat": "NUMPY_NDARRAY",
  "grid": { "dimensions": {"width": w, "height": h},
            "affineTransform": {"scaleX": p, "shearX": 0, "translateX": min_x + col0·p,
                                "shearY": 0, "scaleY": -p, "translateY": max_y - row0·p},
            "crsCode": "EPSG:3857" } }
```

| Sensor | Image expression | Encoding → physical value |
|---|---|---|
| Sentinel-2 | Scenes of the day (`system:index` in list, time ±1 h), `linkCollection(Cloud Score+, ["cs_cdf"])`. Per scene: B2,B3,B4,B5,B8,B8A,B11,B12 `resample("bilinear")` → `uint16`; `cs_cdf` bilinear × 10000 → `uint16` (65535 if no CS+ image); SCL nearest-neighbour; masked to the scene footprint; `mosaic()` | B = DN / 10000 (DN 0 → NaN); `cs_cdf` = DN / 10000 (65535 → NaN); SCL as class (0 → NaN) |
| Sentinel-1 | VV, VH bilinear, `mosaic().unmask(-9999).toFloat()` | already dB; −9999 → NaN |
| Landsat 8/9 | SR_B2…SR_B7 + ST_B10 bilinear, QA_PIXEL nearest, `uint16`, L8/L9 sub-collections merged, `mosaic()` | SR = DN·0.0000275 − 0.2; ST_B10 and QA kept as DN; DN 0 → NaN |
| Copernicus DEM | tiles `mosaic().setDefaultProjection(first tile).resample("bilinear")`, float, −9999 for masked | metres |
| SMAP | newest image, `sm_surface`, `sm_rootzone` bilinear, float | m³/m³ |

The structured NumPy array is split per band and written to `data/runs/{id}/raw/{key}.npz` (uncompressed float32, NaN = no data).
On "User memory limit exceeded" a tile is split into four, down to 64 px, without failover.

**Gateway rules** (`gee/gateway.py`). Every call runs in a worker thread with a timeout of `gee_request_timeout_s` (60 s;
`ee.data.setDeadline` as well).
- 429 / 503 / "Too many concurrent aggregations" / timeouts are retried with backoff `min(20, 1·2ⁿ) + U(0,1)` s, up to `gee_max_retries` (3).
- Quota and permission errors, timeouts, and exhausted retries trigger **failover** to the secondary project. Failover waits
  until in-flight calls have drained, then re-initialises `ee` under a lock and sends the `failover` event
  (toast "Zaxira GEE loyihasiga oʻtildi").
- Every attempt is written to `data/logs/api_calls/YYYY-MM-DD.jsonl` (`usage/tracker.py`).

### Stage 6 — Weather (area mean / min / max)

Five parallel requests. Statistics come from `reduceRegion(mean ⊕ minMax)` over the AOI at scale `clamp(√area / 4, 10 m, 1000 m)`,
so even a tiny AOI gets several sample points of the coarse grid.

| Source tag | Dataset and request | Values |
|---|---|---|
| `era5` | `ECMWF/ERA5_LAND/HOURLY`, `[now − weather_past_days, now]`, one reduction per hourly image | T = t2m − 273.15 °C, Td, precipitation = `total_precipitation_hourly` × 1000 mm, wind = √(u² + v²), u/v, `volumetric_soil_water_layer_1` |
| `gfs_analysis` | `NOAA/GFS0P25`, `forecast_hours = 0`, only after ERA5's last available hour (ERA5 lags ~5 days) | T, Td, RH, wind, cloud cover; **no precipitation** at F0 |
| `gfs_forecast` | Newest run (`creation_time`) whose `max(forecast_hours)` reaches `now + weather_forecast_days` (via `reduceColumns(max.group(creation_time))`), then F = 1…need | as above + precipitation |
| `chirps` | `UCSB-CHC/CHIRPS/V3/DAILY_SAT`, daily | precipitation mm/day |
| — | SMAP time series over `lookback_days` | AOI-mean `sm_surface`, `sm_rootzone` |

GFS `total_precipitation_surface` is accumulated over `((F − 1) % 6) + 1` hours. The interval value is `acc(F) − acc(F_prev)`
inside a bucket and `acc(F)` at a bucket start. Only means can be differenced, so per-interval min/max precipitation is null.
Wind direction is `(270° − atan2(v̄, ū)) mod 360°`. Only forecast records later than "now" are kept.

### Stage 7 — Analysis (pure NumPy; analyzers resolved from the registry by name)

Everything outside the AOI is set to NaN. Statistics (count, mean, std, median, min, max, p10, p90) use valid AOI pixels
only and are **null** when there are none.

1. **Terrain** (`analysis/formulas/terrain.py`, cell = ground size).
   - Horn slope: `dz/dx = ((c+2f+i) − (a+2d+g)) / 8Δ`, `dz/dy = ((g+2h+i) − (a+2b+c)) / 8Δ`, `slope = atan √(dz/dx² + dz/dy²)`.
   - Aspect `(450° − atan2(dz/dy, −dz/dx)) mod 360` (NaN on flat ground).
   - Hillshade (azimuth 315°, altitude 45°); TRI `√Σ(zₙ − z₀)²`; TPI = z − 5×5 mean.
   - Depressions: TPI < −1 m and slope < 3°.
2. **Soil moisture**: SMAP layers plus a least-squares trend `sm(t) = a + b·t` over the series (Δ and slope per day).
3. **Sentinel-1** (each observation).
   - Lee 5×5 filter in **linear power** (ENL 4.4): `W = max(0, (Ci² − Cu²)/Ci²)`, `out = μ + W(x − μ)`.
   - VV and VH in dB, VH − VV, `RVI = 4·VH_lin / (VV_lin + VH_lin)` (not clipped), water mask VV < −15 dB (NaN where VV is missing).
   - ΔVV against the previous S1 observation.
4. **Landsat** (each observation): QA_PIXEL bits 0–4 (fill, dilated cloud, cirrus, cloud, shadow) are masked.
   `LST = DN·0.00341802 + 149.0 − 273.15` °C; Landsat NDVI from SR_B5/SR_B4.
5. **Sentinel-2** (each observation, in time order).
   - Cloud mask: `cs_cdf < cloud_score_threshold` (0.60) or SCL ∈ {3, 8, 9, 10}. No-data: NaN B4/B8 or SCL ∈ {0, 1}.
   - **Indices** (division by zero → NaN): NDVI (B8,B4), EVI `2.5(NIR−Red)/(NIR+6Red−7.5Blue+1)`, NDRE (B8A,B5),
     NDWI (B3,B8), MNDWI (B3,B11), NDMI (B8,B11), NBR (B8,B12), NDBI (B11,B8), BSI `((SWIR1+Red)−(NIR+Blue))/((SWIR1+Red)+(NIR+Blue))`.
   - **RGB features**: brightness (R+G+B)/3, green chromaticity G/(R+G+B), ExG `(2G−R−B)/(R+G+B)`, texture = local 5×5 std of brightness.
   - **Land cover** (slot `landcover`, default rule set, thresholds in `core/constants.py`). Rules are applied in priority order:
     bare soil (BSI > 0, NDVI < 0.15) → sparse vegetation (0.15–0.3) → crop (0.3–0.6) → forest (NDVI > 0.6 with texture or VH > −17 dB)
     → swamp (NDVI 0.1–0.5 and ≥ 3 of 5 evidences: NDWI > −0.1, NDMI > 0, depression, VV < −12 dB, SMAP > 0.30)
     → built-up (NDBI > 0, NDVI < 0.2 and VV > −8 dB, or high texture without SAR) → burnt (NBR < 0.1 and ΔNBR < −0.27)
     → water (MNDWI > 0.1 or NDWI > 0.2) → roads (8-connected built/bare components, ≥ 10 px, principal-axis elongation ≥ 4)
     → bridges (road/built pixels touching water with water on opposite sides) → unknown/cloud for masked pixels.
     SAR comes from the nearest S1 observation within ±3 days. Confidence starts per class, is scaled down when SAR does not
     confirm optical water, and is lowered by 0.25 where the class disagrees with SCL.
   - **Extra ML/CV analyzers** (slot `extra`, stage `s2_observation`) run here automatically and add their own layers.
   - **Class areas** per date use the per-row ground pixel area.
   - **Changes** against the previous real S2 observation: ΔNDVI, ΔNDWI, ΔNDMI, ΔNBR, class-transition matrix
     (≥ 0.1 % shown) and a "class changed" mask. No interpolated frames.
   - **Cross-check** with Landsat ≤ 3 days apart: mean difference, mean absolute difference and correlation of NDVI on common pixels.
6. **Quality** for every layer and date: valid % and cloud-masked % inside the AOI.
   Flags: `NO_DATA` (0 %), `LOW_CONFIDENCE` (< 30 %, "past ishonchlilik"), `HIGH_CLOUD` (> 60 % masked), `GOOD`.
7. **Weather impact** (`weather/impact.py`): rule-based Uzbek statements with numbers, dates and sources.
   - Past rainfall versus SMAP change and ΔVV, or an explicit "maʼlumot yoʻq" when no precipitation source covers the period.
   - Air temperature (record within 1 h) versus Landsat LST.
   - NDVI change versus rain and heat in the same interval.
   - Forecast rainfall ≥ 15 mm with low areas → waterlogging risk; daily forecast ≥ 20 mm → heavy rain.
   - Frost ≤ 0 °C, heat ≥ 38 °C, wind ≥ 12 m/s (past and forecast separately).

Derived arrays are written to `derived/{key}.npz`.

### Stage 8 — Render (`pipeline/render.py`)

Each layer becomes a transparent PNG (NaN → alpha 0):
- Fixed palette ranges where the physics is known (NDVI −0.2…0.9, VV −25…0 dB, slope 0…30°, …); 2–98th percentiles otherwise (elevation, LST, TRI).
- Class layers use fixed colours; masks use one colour plus translucent grey for "no".
- RGB composites are linearly stretched (true colour 0–0.3, false colour 0–0.5 reflectance). Custom R/G/B composites are rendered on request with a 2–98 % stretch.

The legend for every layer (`stops`, `min`, `max`, `unit` or class list) is returned by the API.

### Stage 9 — Persist

`summary.json` holds every numeric result used by the API and the AI (sources, observations, class areas, statistics per date,
terrain, soil moisture, changes, cross-checks, weather summary, impact, quality flags, analyzer producers).
DB rows go to `scenes`, `layers` (with `producer` = `method:analyzer:version`), `layer_stats`, `class_areas` and `weather`.
The run becomes COMPLETED.

### Stage 10 — AI report (`ai/report_generator.py`)

- **Input:** `summary.json` without epoch fields, with per-layer statistics trimmed to mean/min/max/valid %/flag, plus an empty `images` field.
- **System prompt:** use only the given numbers, cite `DD.MM.YYYY HH:MM`, mark low confidence, Latin Uzbek only, Markdown only,
  exactly 7 sections (Umumiy maʼlumot · Relyef · Yer qoplami · Oʻzgarishlar · Ob-havo va taʼsiri · Prognoz va xavflar · Maʼlumot sifati va cheklovlar).
- **Call:** OpenAI Chat Completions with `gpt-6-luna` (if a model rejects `temperature`, the request is repeated without it).
  The deadline is 180 s in total, because some providers keep connections open with whitespace.
- **Validation:** all 7 `##` headings must be present (apostrophe variants accepted). Otherwise one corrective follow-up is sent
  inside the history window; if that also fails, the attempt is saved as FAILED and can be retried.
- At most one successful report per fingerprint (409 `REPORT_EXISTS`). A failed report never fails the run.

---

## 4. Viewing results

| Endpoint | Content |
|---|---|
| `GET /recon/{id}` | summary, bounds, real observation dates, terrain/soil/quality numbers, report status |
| `GET /recon/{id}/layers`, `/layers/{lid}.png` | layer list (time, sensor, dataset, scenes, quality, legend, stats, producer) and PNGs |
| `GET /recon/{id}/composite.png?date=&r=&g=&b=` | custom Sentinel-2 band composite |
| `GET /recon/{id}/pixel?lon=&lat=` | all values at a point, grouped by sensor and date, read directly from the `.npz` member offset |
| `/classes`, `/changes`, `/weather`, `/satellites` | class areas per date, changes and cross-checks, weather and impact, provenance |
| `GET /recon/{id}/terrain3d?scope=context\|aoi` | DEM height field (base64 float32, block mean if reduced), size in metres, bounds, AOI grid bounds. `context` (default): the AOI plus surroundings (each side + max(AOI side, 1.5 km), ≤ 40 km, native 30 m, ≤ 512 px), fetched once from GEE (`dem_context_download`) and cached; `aoi`: the analysis grid only (≤ 384 px) |
| `GET /recon/{id}/labels` | per S2 date: label points for the largest connected components of each class (≥ 0.5 % of the AOI, ≤ 2 per class) |
| `GET/POST/DELETE /recon/{id}/chat` | area chat history / ask / clear |
| `GET /recon/{id}/report`, `POST …/report` | read / generate the report |
| `GET /usage/runs/{id}` | Markdown usage summary per service and purpose |

**2D:** Leaflet with Esri World Imagery. Several layers can be shown at once, each with opacity, legend, time, source and producer badge.
The band composer offers true, false and custom R/G/B. Land-cover names can be shown on the map, and clicking a point opens a paginated popup.

**3D:** Three.js. By default the mesh is the DEM height field of the AOI **and its surroundings**. "Faqat maydon" shows only the
analysis grid, and "Maydonga qaytish" re-centres the camera on the AOI. Vertical exaggeration runs from 1× (true real-world scale)
to 10×. The texture (≤ 4096 px) is Esri World Imagery tiles, loaded in the background, plus exactly the layers visible in 2D
(same order, opacity and date blend), drawn over the AOI part of the surface.
Class names are CSS2D labels on the surface, and the AOI outline follows the terrain. Orbit controls give free rotation, pan and zoom.
Clicking the surface shows the point's values (UV → lon/lat → `/pixel`).

**Date slider:** positions are the real observation dates. While dragging, each layer cross-fades between its own observations
at the two neighbouring dates: the older image stays, the newer one fades in on top. On release the slider eases to the nearest
real date. No intermediate values are computed.

**Chat:** the system prompt restricts the model to this area's results. Off-topic questions get the fixed answer
"Men faqat shu maydon va uning tahlil natijalari haqidagi savollarga javob beraman." The context is the compact summary plus
the last `ai_history_size` messages. A failed call stores nothing.

---

## 5. Extending the "Qatlamlar" layers with classic ML and computer vision

`backend/app/analysis/models/` provides two base classes that implement the `Analyzer` protocol:

- `PixelModelAnalyzer` (classic ML: random forest, gradient boosting, SVM…). It declares `inputs` (any band, index, SAR or
  terrain array names) and implements `predict_pixels(X: N×F) → (N,) | (N×K probabilities)`. NaN pixels are excluded;
  probabilities give the confidence layer.
- `ImageModelAnalyzer` (CV segmentation/detection). It implements `predict_image(tensor C×H×W, valid) → {layer: H×W}`.

`register_model(model)` adds the analyzer to the registry and its `output_specs` (label, palette, legend, group) to the layer
catalog. The pipeline, the API (`producer: {method: "classic_ml" | "cv", analyzer, version}`) and the UI (badge, legend, group)
pick it up automatically.
- `slot = "extra"` adds layers.
- `slot = "landcover"` makes it selectable as the main classifier (setting `landcover_analyzer`).
- Model modules listed in `analysis/models/__init__.py::ENABLED_MODELS` are imported at startup.

---

## 6. Storage

SQLite (schema version 4, `PRAGMA user_version`; later versions migrate with SQL listed in `db/session.py::MIGRATIONS`):
`users`, `runs` (owner, name, fingerprint BLOB(32), grid, settings snapshot, AUTOINCREMENT), `scenes`, `layers` (+ `producer`),
`layer_stats`, `class_areas`, `weather`, `reports` (fingerprint unique), `chat_messages`, `settings` (single row).
Rasters live on disk in `data/runs/{id}/`: `raw/*.npz`, `derived/*.npz`, `png/*.png`, `composite/`, `summary.json`, `labels.json`.

## 7. Cancellation, retention, logs

- `POST /recon/{id}/cancel` (owner only) cancels the task, waits ≤ 2 s, deletes the folder and DB rows, runs `gc.collect()`
  and emits `cancelled`. Runs left RUNNING by a server stop are removed at startup.
- Completed runs (saved areas) are kept until deleted by the owner. Failed runs are purged after 24 h. API logs are kept for 30 days.
  Retention runs at startup and every 10 minutes.
- App logs go only to `data/logs/app/app.log` (terminal mirroring only with `LOG_TO_CONSOLE=true`). API call logs are never printed.
