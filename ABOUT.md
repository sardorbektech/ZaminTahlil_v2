# ABOUT.md — Technical Specification & Master Architecture for ZaminTahlil v2

## 1. System Overview & Purpose
ZaminTahlil is an automated, high-precision area reconnaissance and terrain analysis platform. Given an Area of Interest (AOI ≤ 100 km² polygon or rectangle) selected by the user on a 2D map, it queries Google Earth Engine (GEE) to ingest multi-source satellite imagery (Sentinel-2, Sentinel-1, Landsat 8/9, SMAP, Copernicus DEM) and weather reanalysis/forecast data (ERA5-Land, GFS, CHIRPS). It executes deterministic numerical analyses using pure NumPy formula functions to derive spectral indices, SAR features, thermal surface temperature, terrain derivatives, and a 10-class land-cover classification. A compact numeric summary is supplied to an LLM to generate an authoritative Markdown intelligence report in Uzbek.

## 2. Technology Stack
- **Python 3.12.x** runtime
- **FastAPI 0.115+** (asynchronous REST API with OpenAPI & Server-Sent Events)
- **Uvicorn** ASGI server
- **Pydantic v2 & pydantic-settings** (strict type validation & configuration)
- **SQLAlchemy 2.x + aiosqlite** (SQLite in WAL mode, foreign keys enabled, STRICT tables)
- **earthengine-api & google-auth** (Earth Engine data ingestion)
- **NumPy 2.x, SciPy (ndimage only), Pillow 10+** (in-memory raster processing)
- **HTTPX** (asynchronous client for AI provider APIs)
- **Leaflet + Leaflet-Geoman, marked.js, DOMPurify** (client-side zero-build static UI)

## 3. Data Ingestion & Band Specifications
- **Sentinel-2 Harmonized (`COPERNICUS/S2_SR_HARMONIZED`):** Bands B2, B3, B4, B5, B8, B8A, B11, B12, SCL. Scaled DN / 10000.
- **Cloud Score+ (`GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED`):** Band `cs_cdf` (cloud score threshold default 0.60).
- **Sentinel-1 GRD IW (`COPERNICUS/S1_GRD`):** VV, VH (already in decibels, converted to linear for RVI).
- **Landsat 8 & 9 L2 (`LANDSAT/LC08/C02/T1_L2`, `LANDSAT/LC09/C02/T1_L2`):** Bands SR_B2-SR_B7 (DN * 0.0000275 - 0.2), ST_B10 (DN * 0.00341802 + 149.0 - 273.15 °C), QA_PIXEL.
- **SMAP L4 (`NASA/SMAP/SPL4SMGP/007`):** Bands `sm_surface`, `sm_rootzone`.
- **Copernicus DEM (`COPERNICUS/DEM/GLO30`):** Band `DEM` (elevation in meters).
- **Weather Datasets:**
  - Past hourly: `ECMWF/ERA5_LAND/HOURLY`
  - Near real-time & forecast: `NOAA/GFS0P25`
  - Daily precipitation: `UCSB-CHC/CHIRPS/V3/DAILY`

## 4. Pipeline Workflow (`pipeline/recon.py`)
1. **Validate AOI:** Check GeoJSON polygon validity and ensure total area ≤ 100 km².
2. **Grid Generation:** Define grid in EPSG:3857 aligned with Leaflet tiles; calculate ground resolution `res_m / cos(lat_center)`.
3. **Scene Discovery:** Retrieve metadata (scene IDs, timestamps, cloud percentages) within lookback window.
4. **Fingerprint:** Compute SHA-256 over normalized geometry + sorted scene IDs. If match found, return cached run.
5. **Download:** Chunked `computePixels` requests via GEE Gateway under concurrency limits.
6. **Weather Extraction:** Aggregate area mean, min, max hourly metrics.
7. **Pure Analysis:** Execute registered `Analyzer` instances (indices, SAR, thermal, terrain, land cover, change detection, quality cross-checks).
8. **Render:** Export transparent PNG layers outside AOI and save `.npz` arrays.
9. **Persistence:** Write SQLite records and save artifacts in `data/runs/{run_id}/`.
10. **AI Report:** Construct prompt and stream/generate Markdown report via configured provider.

## 5. Storage Schema (SQLite STRICT)
- `runs`: Primary job run, AOI GeoJSON, area, fingerprint BLOB(32), status, epoch timestamps.
- `scenes`: Ingested scenes, sensor enum, acquisition epoch, cloud percentage.
- `layers`: Computed rasters, kind enum, sensor enum, file path, statistics, quality flags.
- `layer_stats`: Mean, standard deviation, median, p10, p90 percentiles.
- `class_areas`: Area in m² and percentage per land-cover class.
- `weather`: Hourly meteorological metrics with provenance tags.
- `reports`: Unique report markdown per fingerprint.
- `settings`: System-wide configurable runtime defaults.

## 6. Resilience, Logging & Cancellation
- **Concurrency & Rate-Limiting:** GEE requests mediated by an async semaphore (max 6) with exponential backoff and jitter.
- **GEE Failover:** Automatic switch from primary to secondary GCP project on quota exhaustion, 429/503 errors, or request timeout > 60s.
- **Real-Time Terminal Telemetry:** Console output explicitly logs sensor ingestion events, bands retrieved, timestamps, and processing steps.
- **Audit Logs:** All external API requests recorded in `data/logs/api_calls/YYYY-MM-DD.jsonl` (retained for 30 days).
- **Immediate Cancellation:** `POST /recon/{id}/cancel` terminates ongoing asynchronous workers, triggers garbage collection, cleans temporary storage, and broadcasts status update via SSE within ~2 seconds.
- **Retention:** Background task purges runs older than 24 hours on server startup and every 10 minutes.
