"""ZaminTahlil FastAPI ilovasi.

Ishga tushirish: uvicorn backend.app.main:app --reload --no-access-log
"""

import asyncio
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.analysis.analyzers import init_all_analyzers
from backend.app.api.routes_recon import router as recon_router
from backend.app.api.routes_settings import router as settings_router
from backend.app.api.routes_usage import router as usage_router
from backend.app.cleanup.retention import mark_interrupted_runs, start_retention_worker
from backend.app.core.config import BASE_DIR
from backend.app.core.errors import AppError
from backend.app.core.telemetry import logger
from backend.app.db.session import init_db
from backend.app.pipeline.jobs import job_manager


@asynccontextmanager
async def lifespan(app: FastAPI) -> Any:
    """Ishga tushish: analizatorlar, DB, uzilgan run'larni tozalash, retention ishchisi."""
    logger.info("ZaminTahlil serveri ishga tushmoqda")
    init_all_analyzers()
    await init_db()
    await mark_interrupted_runs()
    retention = asyncio.create_task(start_retention_worker(), name="retention")
    try:
        yield
    finally:
        retention.cancel()
        await job_manager.shutdown()
        logger.info("Server toʻxtatildi")


app = FastAPI(
    title="ZaminTahlil API",
    description="Sunʼiy yoʻldosh va ob-havo maʼlumotlari asosida hudud rekognossirovkasi",
    version="2.0.0",
    lifespan=lifespan,
)

# Alohida frontend keyinroq quriladi — API boshqa manbadan ham chaqirilishi mumkin (cookie yo'q)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(AppError)
async def app_error_handler(_request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_dict())


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    errs = exc.errors()
    loc = ".".join(str(x) for x in errs[0].get("loc", [])[1:]) if errs else ""
    return JSONResponse(
        status_code=422,
        content={"code": "VALIDATION_ERROR", "message_uz": f"Soʻrov parametrlari notoʻgʻri: {loc or 'maʼlumot'}"},
    )


@app.exception_handler(StarletteHTTPException)
async def http_error_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    msg = {404: "Manzil topilmadi.", 405: "Bu usul qoʻllab-quvvatlanmaydi."}.get(exc.status_code, "Soʻrov bajarilmadi.")
    return JSONResponse(status_code=exc.status_code, content={"code": f"HTTP_{exc.status_code}", "message_uz": msg})


@app.exception_handler(Exception)
async def global_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    logger.exception(f"Kutilmagan server xatoligi: {exc}")
    return JSONResponse(status_code=500, content={"code": "INTERNAL_ERROR", "message_uz": "Kutilmagan tizim xatoligi."})


app.include_router(recon_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")
app.include_router(usage_router, prefix="/api/v1")

FRONTEND_DIR = BASE_DIR / "frontend"
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
