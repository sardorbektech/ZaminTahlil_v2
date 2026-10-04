"""ZaminTahlil FastAPI asosiy ilovasi (main.py)."""

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.app.analysis.analyzers import init_all_analyzers
from backend.app.api.routes_recon import router as recon_router
from backend.app.api.routes_settings import router as settings_router
from backend.app.api.routes_usage import router as usage_router
from backend.app.cleanup.retention import start_retention_worker
from backend.app.core.config import BASE_DIR
from backend.app.core.errors import AppError
from backend.app.core.telemetry import logger
from backend.app.db.session import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Server ishga tushishi va to'xtatilishida resurslarni boshqarish."""
    logger.info("ZaminTahlil serveri ishga tushmoqda...")
    # 1. Analizatorlarni initsializatsiya qilish
    init_all_analyzers()

    # 2. Ma'lumotlar bazasini yaratish va tekshirish
    await init_db()

    # 3. 24 soatlik tozalash ishchisini (retention) fonda ishga tushirish
    retention_task = asyncio.create_task(start_retention_worker())

    yield

    logger.info("Server to'xtatilmoqda...")
    retention_task.cancel()


app = FastAPI(
    title="ZaminTahlil API",
    description="Sun'iy yo'ldosh va ob-havo ma'lumotlari asosida hudud rekognossirovkasi",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS sozlamalari
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Xatoliklarni standart {code, message_uz} shaklida tutuvchi handler
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(f"Kutilmagan server xatoligi: {exc}")
    return JSONResponse(
        status_code=500,
        content={"code": "INTERNAL_SERVER_ERROR", "message_uz": "Kutilmagan tizim xatoligi yuz berdi"},
    )


# API marshrutlari
app.include_router(recon_router, prefix="/api/v1")
app.include_router(settings_router, prefix="/api/v1")
app.include_router(usage_router, prefix="/api/v1")

# Frontend statik fayllarini ulash
FRONTEND_DIR = BASE_DIR / "frontend"
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
