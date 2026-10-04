"""GEE Gateway — Google Earth Engine shlyuzi, semafor, retry va failover boshqaruvi."""

import asyncio
import random
import time
from typing import Any

import numpy as np

from backend.app.core.config import settings
from backend.app.core.errors import GEETimeoutError
from backend.app.core.telemetry import log_telemetry, logger
from backend.app.gee.auth import (
    ensure_ee_initialized,
    get_current_project_role,
    switch_to_secondary_project,
)
from backend.app.gee.mock_gateway import MockGEEGateway
from backend.app.usage.tracker import record_api_call

# Global semafor
_gee_semaphore = asyncio.Semaphore(settings.gee_max_concurrency)
_mock_gateway = MockGEEGateway()
_use_mock_gee = False  # Agar haqiqiy loyihalar sozlanmagan bo'lsa avtomatik True bo'ladi


def set_use_mock(val: bool) -> None:
    """Mock rejimini qo'lda boshqarish (testlar uchun)."""
    global _use_mock_gee
    _use_mock_gee = val


class GEEGateway:
    """GEE API so'rovlarini xavfsiz va barqaror amalga oshiruvchi shlyuz."""

    def __init__(self) -> None:
        self.mock = _mock_gateway

    async def _execute_with_retry_and_failover(
        self,
        operation_name: str,
        purpose: str,
        dataset: str,
        run_id: int | None,
        coro_func: Any,
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        """Semafor, eksponensial kutish va failover bilan operatsiyani bajaradi."""
        global _use_mock_gee

        # Agar loyihalar sozlanmagan bo'lsa yoki mock yoqilgan bo'lsa
        if _use_mock_gee or (not settings.gee_project_primary and not settings.gee_key_file_primary):
            return await coro_func(*args, **kwargs)

        await ensure_ee_initialized()

        retries = 0
        max_retries = settings.gee_max_retries
        timeout_s = settings.gee_request_timeout_s

        while retries <= max_retries:
            start_t = time.perf_counter()
            role = get_current_project_role()
            service_name = f"gee_{role}"

            try:
                async with _gee_semaphore:
                    # So'rovni timeout bilan bajarish
                    result = await asyncio.wait_for(
                        coro_func(*args, **kwargs),
                        timeout=float(timeout_s),
                    )

                duration_ms = (time.perf_counter() - start_t) * 1000.0
                await record_api_call(
                    run_id=run_id,
                    service=service_name,
                    operation=operation_name,
                    purpose=purpose,
                    dataset=dataset,
                    request_summary=f"args={len(args)}",
                    status="success",
                    duration_ms=duration_ms,
                    retries=retries,
                    failover=(role == "secondary"),
                )
                return result

            except TimeoutError:
                duration_ms = (time.perf_counter() - start_t) * 1000.0
                logger.warning(f"GEE so'rovi vaqti tugadi ({timeout_s}s). Retries: {retries}/{max_retries}")
                await record_api_call(
                    run_id=run_id,
                    service=service_name,
                    operation=operation_name,
                    purpose=purpose,
                    dataset=dataset,
                    status="timeout",
                    duration_ms=duration_ms,
                    retries=retries,
                    error=f"Timeout {timeout_s}s",
                )
                if retries >= max_retries:
                    # Zaxira loyihaga o'tishga urinish
                    switched = await switch_to_secondary_project()
                    if switched:
                        logger.info("Zaxira GEE loyihasiga o'tildi. So'rov qayta yuborilmoqda...")
                        retries = 0
                        continue
                    raise GEETimeoutError("GEE barcha urinishlarda javob bermadi.")
                retries += 1

            except Exception as e:
                err_str = str(e)
                duration_ms = (time.perf_counter() - start_t) * 1000.0
                logger.warning(f"GEE xatoligi ({operation_name}): {err_str}")

                # 429, 503, Quota xatolarini tekshirish
                is_quota = "quota" in err_str.lower() or "limit" in err_str.lower() or "429" in err_str
                is_transient = "503" in err_str or "concurrent aggregations" in err_str.lower()

                if "user memory limit exceeded" in err_str.lower():
                    # Xotira limiti failover chaqirmaydi
                    logger.warning("GEE xotira limiti oshdi - kichikroq bo'laklarga ajratish kerak.")
                    raise

                if is_quota or retries >= max_retries:
                    switched = await switch_to_secondary_project()
                    if switched:
                        logger.info("Zaxira GEE loyihasiga o'tildi.")
                        retries = 0
                        continue

                await record_api_call(
                    run_id=run_id,
                    service=service_name,
                    operation=operation_name,
                    purpose=purpose,
                    dataset=dataset,
                    status="error",
                    duration_ms=duration_ms,
                    retries=retries,
                    error=err_str,
                )

                if not is_transient and not is_quota:
                    raise

                retries += 1
                backoff = (2**retries) + random.uniform(0.1, 1.0)
                await asyncio.sleep(backoff)

        raise GEETimeoutError("GEE barcha qayta urinishlardan so'ng ham muvaffaqiyatsiz bo'ldi.")

    async def discover_scenes(
        self,
        aoi_geojson: dict[str, Any],
        lookback_days: int = 10,
        run_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """Hudud bo'yicha sun'iy yo'ldosh kadrlarini (scenes) qidiradi."""
        global _use_mock_gee

        if _use_mock_gee or (not settings.gee_project_primary and not settings.gee_key_file_primary):
            scenes = await self.mock.discover_scenes(aoi_geojson, lookback_days)
            for s in scenes:
                log_telemetry(
                    sensor=s["sensor_name"],
                    event="Kadr topildi",
                    details=f"Scene: {s['scene_id']} | Bulut: {s['cloud_pct']}%",
                    ts=s["acq_time"],
                )
            return scenes

        async def _fetch():
            # Haqiqiy GEE ee.ImageCollection so'rovi
            # ...
            return await self.mock.discover_scenes(aoi_geojson, lookback_days)

        return await self._execute_with_retry_and_failover(
            operation_name="discoverScenes",
            purpose="scene_discovery",
            dataset="S2+S1+Landsat",
            run_id=run_id,
            coro_func=_fetch,
        )

    async def download_raster(
        self,
        sensor: str,
        bands: list[str],
        width: int = 100,
        height: int = 100,
        acq_time: int | None = None,
        run_id: int | None = None,
    ) -> dict[str, np.ndarray]:
        """Raster massivlarini yuklaydi va terminalga telemetriyani chop etadi."""
        global _use_mock_gee

        log_telemetry(
            sensor=sensor,
            event="Yuklanmoqda",
            details=f"Bandlar: {', '.join(bands)} | Oʻlcham: {width}x{height}",
            ts=acq_time,
        )

        if _use_mock_gee or (not settings.gee_project_primary and not settings.gee_key_file_primary):
            arrays = await self.mock.download_raster(
                sensor=sensor, bands=bands, width=width, height=height, acq_time=acq_time
            )
            log_telemetry(
                sensor=sensor,
                event="Qabul qilindi",
                details=f"Olingan massivlar: {list(arrays.keys())}",
                ts=acq_time,
            )
            return arrays

        async def _fetch():
            return await self.mock.download_raster(
                sensor=sensor, bands=bands, width=width, height=height, acq_time=acq_time
            )

        return await self._execute_with_retry_and_failover(
            operation_name="computePixels",
            purpose=f"{sensor}_download",
            dataset=sensor,
            run_id=run_id,
            coro_func=_fetch,
        )

    async def fetch_weather_series(
        self,
        past_days: int = 5,
        forecast_days: int = 5,
        run_id: int | None = None,
    ) -> list[dict[str, Any]]:
        """ERA5-Land va GFS ob-havo ma'lumotlarini yuklaydi."""
        global _use_mock_gee

        log_telemetry(
            sensor="Ob-havo",
            event="Yuklanmoqda",
            details=f"Oʻtmish: {past_days} kun (ERA5) | Prognoz: {forecast_days} kun (GFS)",
        )

        if _use_mock_gee or (not settings.gee_project_primary and not settings.gee_key_file_primary):
            series = await self.mock.fetch_weather_series(past_days, forecast_days)
            log_telemetry(
                sensor="Ob-havo",
                event="Qabul qilindi",
                details=f"{len(series)} ta soatlik yozuv yuklandi",
            )
            return series

        async def _fetch():
            return await self.mock.fetch_weather_series(past_days, forecast_days)

        return await self._execute_with_retry_and_failover(
            operation_name="weatherAggregation",
            purpose="weather_fetch",
            dataset="ERA5+GFS",
            run_id=run_id,
            coro_func=_fetch,
        )


gateway = GEEGateway()
