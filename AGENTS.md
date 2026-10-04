# AGENTS.md — instructions for coding agents working on ZaminTahlil v2

Read `SIMPLE.md` (requirements), `ABOUT.md` (how every stage works) and `docs/DECISIONS.md` (choices not in the spec)
before changing code. If something is not covered, choose the simplest option and add a decision to `docs/DECISIONS.md`.

## Commands (Windows paths; use `.venv/bin/` on Linux/macOS)

```bash
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --no-access-log
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe -m ruff check .
```

The app runs at http://localhost:8000 (UI) and http://localhost:8000/docs (OpenAPI). Done means: tests pass, ruff is clean,
and UI changes are checked in a browser.

## Non-negotiable rules

1. **Accuracy first.** Never fabricate, interpolate or estimate a value and present it as measured. Missing data is
   `None`/NaN in code and "maʼlumot yoʻq" in the UI — never 0. Every value carries its source dataset and exact time.
   There is no synthetic data source in `backend/`; fakes live only in `tests/fakes.py`.
2. **Every external call goes through a tracked path.** GEE goes only through `gee/gateway.py` (`GEEGateway.call`), and
   AI goes only through `ai/client.py` providers. Both log every attempt via `usage/tracker.py` to `data/logs/api_calls/*.jsonl`.
3. **No hard-coding inside functions.** Dataset IDs and band names go in `gee/datasets/__init__.py` (verify them in the GEE
   catalog first). Thresholds and limits go in `core/constants.py`. User-tunable values go in `core/run_settings.py` and the `settings` table.
4. **Pure analysis.** `analysis/` functions are NumPy only (no I/O), use float32 and NaN for invalid pixels, and carry an Uzbek
   docstring with the formula and bands. The pipeline gets analyzers from the registry by name (`analysis/registry.py`).
5. **One job at a time** (409), always cancellable (`pipeline/jobs.py`), and cancellation deletes files and DB rows.
6. **Ownership.** Every `/recon/*` and `/usage/*` endpoint takes `user: CurrentUser = Depends(current_user)` and loads runs
   through `_get_run(db, run_id, user)` (other users get 404). Only `POST /auth/login` may create users.
7. **The page never scrolls; panels do.** `html/body/#app` stay `overflow: hidden`. Long panel content goes through
   `frontend/js/ui/paginate.js`, which renders an internally scrolling list (DECISIONS 28). While a run is active, everything
   except "Toʻxtatish" is disabled.
8. **Languages.** UI text and AI output are Uzbek Latin (`ʻ` U+02BB in oʻ/gʻ, `ʼ` U+02BC for the tutuq belgisi). All UI strings
   live in `frontend/js/i18n/uz.js`. Code comments and docstrings are Uzbek. Identifiers, API paths, JSON keys and DB columns are
   English. `docs/*`, `ABOUT.md` and this file are English.
9. **Time.** Store UTC epoch seconds (INTEGER). Display `DD.MM.YYYY HH:MM` in Asia/Tashkent via `core/time.py::fmt_local`.
   API responses use `*_ts` + `*_local` (`ts_fields`).
10. **Errors** use the shape `{code, message_uz}` (`core/errors.py`).
11. **Logging.** No `print`. Logs go to `data/logs/app/` (`LOG_TO_CONSOLE=true` mirrors them to the terminal for development).
12. **Secrets** stay in `.env` and `secrets/` (both git-ignored). `.env.example` contains no values. The API never returns keys.

## Map of the code

| Area | Where |
|---|---|
| App, routers, error handlers | `backend/app/main.py`, `backend/app/api/routes_*.py` |
| Login (Basic header, PBKDF2) | `backend/app/auth/security.py`, `api/routes_auth.py` |
| DB models, migrations | `backend/app/db/models.py`, `db/session.py` (`SCHEMA_VERSION`, `MIGRATIONS`) |
| GEE access | `gee/gateway.py` (retry/failover), `gee/sources.py` (ee expressions), `gee/convert.py` (scaling) |
| Pipeline (10 stages) | `pipeline/recon.py`; grid `pipeline/grid.py`; files `pipeline/storage.py`; jobs/SSE/cancel `pipeline/jobs.py` |
| Rendering and layer catalog | `pipeline/render.py` (`LAYER_SPECS`, `register_layer_spec`) |
| 3D height field, context grid, labels | `pipeline/terrain3d.py` (`context_grid`), `GET /recon/{id}/terrain3d` (scope: context / aoi) |
| Formulas and rules | `analysis/formulas/*`, `analysis/landcover.py`, `analysis/changes.py`, `analysis/quality.py` |
| ML / CV extension point | `analysis/models/` (`PixelModelAnalyzer`, `ImageModelAnalyzer`, `register_model`, `ENABLED_MODELS`) |
| Weather impact | `weather/impact.py` |
| AI report and area chat | `ai/report_generator.py`, `ai/chat.py`, `ai/client.py` (default `openai` / `gpt-6-luna`) |
| Retention | `cleanup/retention.py` (saved areas kept; failed runs and orphan folders removed) |
| Frontend | `frontend/js/app.js` (state machine), `map/` (Leaflet, overlays + cross-fade, 3D, labels, popup), `ui/` (panels) |

## Adding things

- **New layer from a model:** subclass `PixelModelAnalyzer` or `ImageModelAnalyzer`, set `name`, `version`, `inputs` and
  `output_specs` (`LayerSpec(kind=LayerKind.MODEL_OUTPUT, …)`), choose `slot` (`"extra"` or `"landcover"`), call `register_model()`
  in its module, and add the module path to `ENABLED_MODELS`. No pipeline, API or UI change is needed. Add a test like
  `tests/test_users_areas.py::test_extra_ml_model_layer_flows_to_api`.
- **New dataset:** verify the ID and bands in the GEE catalog, add constants to `gee/datasets`, build the expression in
  `gee/sources.py`, extend `tests/fakes.py::FakeSource`, and record the decision.
- **DB change:** bump `SCHEMA_VERSION` and add the SQL to `MIGRATIONS[new_version]`. Never drop tables of a version ≥ 4,
  because user data (saved areas) must survive.
- **New UI text:** add it to `uz.js` and use `data-i18n` / `uz.*`.

## Testing notes

- Tests never touch the network: `tests/conftest.py` blocks HTTP transports, swaps GEE for `FakeSource` and AI for `FakeAIClient`,
  and gives every test its own temp data folder and SQLite file.
- The `client` fixture is logged in as `tester:p`. Use `tests/conftest.py::make_client(username, password)` for other users
  and the `anon` fixture for unauthenticated calls.
- Use `wait_for_run(run_id)` to wait for a pipeline run in tests.
