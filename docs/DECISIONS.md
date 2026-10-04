# DECISIONS.md — Architecture and Technical Decisions

Decisions taken where SIMPLE.md is silent or ambiguous, with the reason for each. Newest decisions are at the end.

---

## 1. Terminal output vs. "logs go to files only"
- **Decision:** All application logs go to `data/logs/app/app.log` (daily rotation, 30 files). Nothing is printed to the terminal by default. Setting `LOG_TO_CONSOLE=true` in `.env` mirrors the app log (sensor, scene, bands, acquisition time per download) to stderr during development. The API usage log (`data/logs/api_calls/*.jsonl`) is never printed.
- **Reason:** SIMPLE.md §10/§14 forbid terminal output; `.agents/rules/project.md` asked for live terminal telemetry. The opt-in flag satisfies both without changing the default.

## 2. No synthetic data source in the application
- **Decision:** The previous `MockGEEGateway` was removed from `backend/`. The pipeline only talks to a `DataSource` interface (`gee/types.py`); production uses `GEESource`, tests use `tests/fakes.py::FakeSource`. If GEE is not configured, `POST /recon` returns `GEE_NOT_CONFIGURED` instead of silently producing synthetic rasters.
- **Reason:** SIMPLE.md §1 — never fabricate values and show them as measured. The old code returned mock arrays even when real credentials were set, and `/changes` returned hard-coded numbers.

## 3. SQLite STRICT, WAL, AUTOINCREMENT and schema versioning
- **Decision:** All tables are `STRICT`; WAL and `foreign_keys=ON` are set per connection. `runs` uses `AUTOINCREMENT` so purged run IDs are never reused (the JSONL usage log is keyed by `run_id` and kept for 30 days). The schema version lives in `PRAGMA user_version`; on mismatch the database is rebuilt (run data only lives 24 h) and the `runs` sequence is seeded from the largest `run_id` found in the usage logs.
- **Reason:** Type safety, concurrent read/write, and no collisions between old log entries and new runs.

## 4. Dataset versions (verified in the GEE catalog on 04.10.2026)
| Spec text | Used | Why |
|---|---|---|
| `NASA/SMAP/SPL4SMGP/<latest>` | `NASA/SMAP/SPL4SMGP/008` | Newest version in the catalog. |
| `COPERNICUS/DEM/GLO30` | `COPERNICUS/DEM/GLO30_2024_1` | GEE marks GLO30 as deprecated and superseded by GLO30_2024_1. |
| `UCSB-CHC/CHIRPS/V3/DAILY` | `UCSB-CHC/CHIRPS/V3/DAILY_SAT` | `V3/DAILY` does not exist; V3 has `DAILY_RNL` (ERA5-based) and `DAILY_SAT` (IMERG-based, near-real-time). The near-real-time variant is chosen for recent days. |
| GFS bands | adds `dew_point_temperature_2m_above_ground` | Available since 15.01.2025; avoids deriving dew point. |

All IDs and band names live in `backend/app/gee/datasets/__init__.py`.

## 5. GFS precipitation differencing
- **Decision:** `total_precipitation_surface` accumulates over a bucket of `((F − 1) % 6) + 1` hours (catalog text). The increment for forecast hour F is `acc(F) − acc(F_prev)` inside a bucket, and `acc(F)` at the start of a new bucket (`gee/sources.py::gfs_precip_increments`). Only area **means** are differenced; per-increment min/max are stored as null because they cannot be derived from bucket min/max.
- **Forecast run choice:** the newest GFS run whose maximum forecast hour covers `now + weather_forecast_days`; if none is complete, the newest run is used and a note is shown.

## 6. Weather gap between ERA5-Land and now
- **Decision:** ERA5-Land hourly is used up to its last available hour; after that, GFS forecast-hour-0 analyses (6-hourly) fill the gap. GFS analyses carry no precipitation, so recent rainfall is reported as "maʼlumot yoʻq" unless CHIRPS has it. No value is interpolated.

## 7. Scenes, observations and fingerprint
- **Decision:** Scene discovery covers Sentinel-2, Sentinel-1 and Landsat 8/9 within `lookback_days` (S2/Landsat filtered by `max_scene_cloud_pct`, S1 by IW, VV+VH and orbit pass). Same-sensor scenes on the same UTC day form one observation (mosaic). The fingerprint is `sha256(normalized geometry + sorted "dataset/scene_id")`. DEM and SMAP are not part of the fingerprint: SMAP updates every 3 h and would make every run "new".
- **Duplicate run:** when the fingerprint matches a completed run, the new run row and folder are deleted, the `duplicate` SSE event carries `existing_run_id`, and the frontend loads that run.

## 8. Grid and areas
- **Decision:** The grid origin is snapped to multiples of the projected pixel size so the same AOI always produces the same grid. Class areas use the true ground area of each pixel row, `(p · cos φ_row)²`, not the projected pixel area.

## 9. Download format
- **Decision:** `computePixels` with `NUMPY_NDARRAY`, tiles of 512×512, run in parallel under the gateway semaphore. Optical/Landsat bands are requested as `uint16` (0 = masked); Cloud Score+ is requested as `uint16` (value × 10000, 65535 = no CS+ image); S1/DEM/SMAP are `float32` with −9999 for masked. On "User memory limit exceeded" a tile is split into four (down to 64 px) — no failover.

## 10. Cloud masking and quality
- **Decision:** A Sentinel-2 pixel is cloud-masked when `cs_cdf < cloud_score_threshold` or SCL ∈ {3, 8, 9, 10}; SCL ∈ {0, 1} is no-data. Landsat uses QA_PIXEL bits 0–4. Valid % and cloud-masked % are computed inside the AOI only. Flags: `NO_DATA` (0 %), `LOW_CONFIDENCE` (< 30 %, shown as "past ishonchlilik"), `HIGH_CLOUD` (> 60 % masked), `GOOD`. Statistics over zero valid pixels are null, never 0.
- **RGB layers** are rendered without the cloud mask (they are the imagery itself) but report the cloud-masked share.

## 11. SAR processing
- **Decision:** The Lee 5×5 filter runs in linear power (dB → linear → Lee → dB), ENL 4.4 (IW GRDH). RVI is not clipped. The SAR water mask is NaN where VV is missing. For land cover, the nearest Sentinel-1 observation within 3 days of the Sentinel-2 date is used; otherwise SAR evidence is absent.

## 12. Land-cover rules
- **Decision:** Rules follow SIMPLE.md §7.4 with all thresholds in `core/constants.py`. Details not in the spec:
  - Swamp needs NDVI 0.1–0.5 and at least 3 of 5 evidences (NDWI > −0.1, NDMI > 0, depression, VV < −12 dB, SMAP surface moisture > 0.30).
  - Dense NDVI (> 0.6) without texture or VH evidence is classed as crop with lower confidence.
  - Without SAR, built-up requires high texture in addition to NDBI > 0 and NDVI < 0.2.
  - Burnt area is only possible when a previous real observation gives ΔNBR (< −0.27).
  - Roads: 8-connected components of built-up/bare pixels with ≥ 10 pixels and principal-axis elongation ≥ 4.
  - Bridges: road/built-up pixels touching water with water on opposite sides within 3 pixels.
  - Confidence is lowered by 0.25 when the class disagrees with SCL and is scaled down when SAR does not confirm optical water.
- **SMAP** (≈11 km) is used as a coarse swamp evidence; the latest image within the lookback window is applied to all Sentinel-2 dates.

## 13. Change detection
- **Decision:** ΔNDVI/ΔNDWI/ΔNDMI/ΔNBR and class transitions between consecutive Sentinel-2 observations; ΔVV between consecutive Sentinel-1 observations; soil-moisture change and least-squares trend from the SMAP time series (area means). No interpolated frames.

## 14. Date slider semantics
- **Decision:** The slider positions are the union of real observation times (S2, S1, Landsat). At a selected time each visible layer shows its own latest observation at or before that time, labelled with its own timestamp; static layers (DEM, SMAP) are always shown. Switching dates cross-fades the old and new images.

## 15. AI report
- **Decision:** Input is `summary.json` without epoch fields (`*_ts`), with per-layer statistics trimmed to mean/min/max/valid %/flag. The answer must contain the seven `##` sections (apostrophe variants accepted); otherwise one corrective follow-up is sent inside the history window, then the attempt is stored as `FAILED` (retry allowed). A hard total deadline (`AI_REQUEST_TIMEOUT_S`, default 180 s) applies because some providers keep connections alive with whitespace. Missing keys or provider errors never produce a canned report.
- **History window:** messages are kept per fingerprint and trimmed to `ai_history_size`; there is no chat UI.

## 16. Cancellation
- **Decision:** `POST /recon/{id}/cancel` cancels the asyncio task (in-flight HTTP waits end immediately; worker threads finish in the background and their results are discarded), waits at most 2 s, deletes the run folder and DB rows, runs `gc.collect()` and emits `cancelled`. Runs left in `RUNNING` after a server restart are deleted at startup.

## 17. No-scroll frontend
- **Decision:** Every list, table and Markdown document is paginated by measuring what fits (`frontend/js/ui/paginate.js`); oversized tables/lists are split by rows with the header repeated. The pixel popup is paginated too. While a run is active, every button, input and map interaction is disabled except "Toʻxtatish".
- **Restore:** after a reload, `/recon/active` restores a running job (AOI + SSE replay). The last completed run ID is kept in `localStorage` (per-viewer convenience only) and reloaded if it still exists.

## 18. Pixel queries
- **Decision:** Derived and raw arrays are stored as uncompressed `.npz`; a pixel query reads single values through the zip member offset (`pipeline/storage.py::read_pixel`) instead of decompressing whole arrays. This trades disk space (deleted after 24 h) for fast map clicks.

## 19. Secrets
- **Decision:** `.env` holds GEE project IDs, key file paths and AI keys; `secrets/` (service-account JSON) and `.env` are git-ignored. `.env.example` contains no values. `GET /settings` only returns booleans saying which services are configured.

## 20. Saved areas instead of 24-hour retention (user request, 05.10.2026)
- **Decision:** Completed runs are the user's saved areas (ID + name). They are never purged automatically and are deleted only by the owner (`DELETE /recon/{id}`). Failed runs are still purged after 24 h, API logs after 30 days. This overrides SIMPLE.md §6 "Retention".
- **Reason:** the user wants to reopen previously analysed areas at any time.

## 21. Users: username + password, no tokens (user request)
- **Decision:** HTTP Basic credentials on every request; `POST /auth/login` creates unknown usernames (≥ 1 character) and verifies known ones. Passwords are PBKDF2-HMAC-SHA256 (200 000 iterations, random salt). The browser keeps credentials in `sessionStorage` (cleared when the tab closes) and re-sends `/auth/login` once after a 401, so deleting the DB file recreates the user transparently. Settings are global (one row) and editable by any logged-in user. The single-job limit stays global (one GEE pipeline at a time); other users see `busy: true` but no details.
- **Fingerprint** includes the user ID, so de-duplication and "one report per fingerprint" are per user.

## 22. Database survives manual deletion; migrations from v4 on
- **Decision:** A missing DB file is recreated at startup (stale `-wal/-shm/-journal` files are removed first). Orphan run folders are deleted. Completed runs whose `summary.json` is missing are dropped. The `runs` sequence is seeded from the largest `run_id` in the usage logs. Schema v4 is the first version that is migrated instead of rebuilt (`db/session.py::MIGRATIONS`). The upgrade from v3 rebuilt the DB once (old runs had no owner).

## 23. 3D view (user request; overrides SIMPLE.md §13 "3D terrain")
- **Decision:** Three.js r160 from jsDelivr (import map). The relief is the run's Copernicus DEM (GLO30_2024_1, 30 m) for the whole grid, block-averaged to ≤ 384 points per side — no interpolation beyond the bilinear resampling GEE already applied. No extra satellite is needed: Copernicus GLO-30 is the most accurate free global DEM in the catalog at this scale. The texture is Esri World Imagery tiles (CORS-enabled) plus the same visible layers as in 2D, so 3D always shows exactly what 2D shows. Without Esri (CORS failure) only the layers are drawn and a note is shown. Labels use the backend-computed class components (`/labels`).

## 24. Smooth date transitions
- **Decision:** The date slider is continuous. Between two real dates each layer cross-fades between its own observations ("over" compositing: the older image stays, the newer one fades in on top, so there is no mid-transition dimming). On release it eases to the nearest real date in 600 ms. All images of visible layers are prefetched. This is a visual cross-fade only; no intermediate values are computed.

## 25. AI defaults and area chat (user request)
- **Decision:** Default provider `openai`, model `gpt-6-luna` (verified to exist via `/v1/models` on 05.10.2026; ~18 s per report). OpenRouter and Ollama remain selectable. If a model rejects `temperature`, the request is repeated without it. Prompts require Latin-script Uzbek only (the model occasionally mixed in Cyrillic words). The area chat (`/recon/{id}/chat`) sends a system prompt that restricts answers to this area's results and returns a fixed refusal otherwise, then the compact summary and the last `ai_history_size` messages. This overrides SIMPLE.md §8 "no chat UI".

## 26. ML / CV extension point for layers
- **Decision:** `analysis/models/` defines `PixelModelAnalyzer` (classic ML on per-pixel feature vectors) and `ImageModelAnalyzer` (CV on C×H×W tensors). Models register their analyzer and layer specs with `register_model()`. Slot `extra` adds layers; slot `landcover` replaces the rule-based classifier via the `landcover_analyzer` setting. Every layer stores `producer = method:analyzer:version`, shown as a badge in the UI. No model ships yet; `ENABLED_MODELS` lists the modules to import.

## 27. Robust pagination and map sizing
- **Decision:** Paginated containers re-measure with a `ResizeObserver` on the page body, and the map defers `fitBounds` until it is at least 100×100 px. Pages loaded in a hidden tab otherwise measured 0 px.

## 28. Menu panels scroll instead of paging (user request, 05.10.2026)
- **Decision:** The right-hand panel tabs, the chat and the "Maydonlarim" dialog use internal vertical scrolling (thin visible scrollbar). The page itself still never scrolls (`overflow: hidden` on `html/body/#app`), and the map pixel popup keeps its compact pager. `paginate.js` keeps its API (`keepPage` keeps the scroll position, `lastPage` scrolls to the end). This partially overrides SIMPLE.md §12 "no scrolling anywhere". Decision 17 (paging) and 27 (re-measuring) no longer apply to the panels.

## 29. 3D with surroundings, real-scale exaggeration, larger fonts (user request)
- **Decision:** By default the 3D view shows the AOI inside its surroundings. `GET /recon/{id}/terrain3d?scope=context` builds a grid around the AOI (each side extended by max(AOI side, 1.5 km), total side ≤ 40 km) at the DEM's native 30 m (coarser only to stay ≤ 512 px). It downloads Copernicus DEM for it once through the gateway (`purpose = dem_context_download`, logged) and caches it as `raw/dem_context.npz`. Analysis layers are drawn only over the AOI part of the texture (they exist only there); the rest is Esri imagery. "Faqat maydon" switches to `scope=aoi`, and "Maydonga qaytish" re-centres the camera on the AOI. Vertical exaggeration ranges from 1× (true real-world scale, the default) to 10×. The Esri base loads in the background (≤ 144 tiles, texture ≤ 4096 px) so the layers appear immediately.
- **Layers:** "Hammasini olib tashlash" unchecks every visible layer and the composite in one click.
- **UI:** panel fonts were enlarged by about 1–1.5 px. Text inputs (including the login form and browser autofill) use a dark background with light text.
