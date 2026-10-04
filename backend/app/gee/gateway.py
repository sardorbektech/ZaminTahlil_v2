"""GEE Gateway — barcha Earth Engine chaqiruvlari uchun yagona kirish nuqtasi.

Vazifalari (SIMPLE.md §9):
- har bir sinxron `ee` chaqiruvini alohida thread'da bajarish;
- semafor bilan parallel so'rovlarni cheklash (standart 6);
- 429, 503, "Too many concurrent aggregations" va timeout'larda jitter'li qayta urinish;
- kvota/ruxsat xatosi, urinishlar tugashi yoki timeout'da zaxira loyihaga o'tish
  (jarayondagi so'rovlar tugashini kutib, qulf ostida `ee` ni qayta initsializatsiya qilish);
- "User memory limit exceeded" da failover qilmasdan GEEMemoryLimitError ko'tarish
  (chaqiruvchi so'rovni kichikroq bo'laklarga bo'ladi);
- har bir urinishni usage/tracker.py orqali jurnalga yozish.
"""

import asyncio
import json
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import numpy as np

from backend.app.core import constants as C
from backend.app.core.errors import (
    GEEError,
    GEEMemoryLimitError,
    GEENotConfiguredError,
    GEEQuotaError,
    GEETimeoutError,
)
from backend.app.core.run_settings import RunSettings
from backend.app.core.telemetry import logger
from backend.app.gee.auth import PRIMARY, SECONDARY, init_ee_for_role, is_role_configured
from backend.app.usage.tracker import record_api_call

EventCallback = Callable[[str, dict[str, Any]], Awaitable[None]]


@dataclass
class CallContext:
    """Chaqiruv konteksti: qaysi run uchun va failover haqida kimga xabar berish."""

    run_id: int | None = None
    on_event: EventCallback | None = None


# Xato turlari
ERR_MEMORY = "memory"
ERR_QUOTA = "quota"
ERR_AUTH = "auth"
ERR_TRANSIENT = "transient"
ERR_TIMEOUT = "timeout"
ERR_FATAL = "fatal"

_TRANSIENT_MARKERS = (
    "429",
    "too many requests",
    "rate limit",
    "503",
    "service unavailable",
    "too many concurrent aggregations",
    "deadline",
    "timed out",
    "timeout",
    "capacity exceeded",
    "internal error",
    "connection",
    "temporarily",
)
_AUTH_MARKERS = (
    "permission",
    "not authorized",
    "unauthorized",
    "unauthenticated",
    "401",
    "403",
    "credentials",
    "serviceusage",
    "not signed up",
    "not registered",
)


def classify_error(exc: BaseException) -> str:
    """GEE istisnosini turiga ajratadi (failover/qayta urinish qarori uchun)."""
    if isinstance(exc, GEENotConfiguredError):
        return ERR_AUTH
    if isinstance(exc, TimeoutError):
        return ERR_TIMEOUT
    msg = str(exc).lower()
    if "user memory limit exceeded" in msg:
        return ERR_MEMORY
    if "too many concurrent aggregations" in msg:
        return ERR_TRANSIENT
    if "quota" in msg:
        return ERR_QUOTA
    if any(m in msg for m in _AUTH_MARKERS):
        return ERR_AUTH
    if any(m in msg for m in _TRANSIENT_MARKERS):
        return ERR_TRANSIENT
    return ERR_FATAL


def result_size_bytes(result: Any) -> int:
    """Javob hajmini baholaydi (jurnal uchun)."""
    if isinstance(result, np.ndarray):
        return int(result.nbytes)
    if result is None:
        return 0
    try:
        return len(json.dumps(result, default=str))
    except (TypeError, ValueError):
        return 0


class GEEGateway:
    """GEE so'rovlarini xavfsiz va barqaror bajaruvchi shlyuz."""

    def __init__(
        self,
        initializer: Callable[[str, int], None] = init_ee_for_role,
        role_configured: Callable[[str], bool] = is_role_configured,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._initializer = initializer
        self._role_configured = role_configured
        self._sleep = sleep
        self.role = PRIMARY
        self._initialized_role: str | None = None
        self._init_lock = asyncio.Lock()
        self._switch_lock = asyncio.Lock()
        self._ready = asyncio.Event()
        self._ready.set()
        self._inflight = 0
        self._inflight_cond = asyncio.Condition()
        self.timeout_s = float(C.DEFAULT_GEE_REQUEST_TIMEOUT_S)
        self.max_retries = C.DEFAULT_GEE_MAX_RETRIES
        self._sem = asyncio.Semaphore(C.DEFAULT_GEE_MAX_CONCURRENCY)
        self.failover_happened = False

    # ------------------------------------------------------------------
    # Sozlash
    # ------------------------------------------------------------------
    def configure(self, run_settings: RunSettings) -> None:
        """Run boshida sozlamalarni qo'llaydi va asosiy loyihaga qaytadi."""
        self.timeout_s = float(run_settings.gee_request_timeout_s)
        self.max_retries = int(run_settings.gee_max_retries)
        self._sem = asyncio.Semaphore(int(run_settings.gee_max_concurrency))
        self.failover_happened = False
        if self.role != PRIMARY and self._role_configured(PRIMARY):
            self.role = PRIMARY
            self._initialized_role = None

    def is_configured(self) -> bool:
        """Kamida bitta GEE loyihasi sozlanganmi."""
        return self._role_configured(PRIMARY) or self._role_configured(SECONDARY)

    # ------------------------------------------------------------------
    # Initsializatsiya va failover
    # ------------------------------------------------------------------
    async def _ensure_initialized(self, ctx: CallContext) -> None:
        async with self._init_lock:
            if self._initialized_role == self.role:
                return
            if not self._role_configured(self.role):
                if self.role == PRIMARY and self._role_configured(SECONDARY):
                    self.role = SECONDARY
                    self.failover_happened = True
                    await self._notify(ctx, "failover", {"reason": "primary_not_configured"})
                else:
                    raise GEENotConfiguredError()
            await asyncio.wait_for(
                asyncio.to_thread(self._initializer, self.role, int(self.timeout_s)),
                timeout=self.timeout_s,
            )
            self._initialized_role = self.role
            logger.info(f"GEE initsializatsiya qilindi ({self.role})")

    async def _notify(self, ctx: CallContext, kind: str, data: dict[str, Any]) -> None:
        if ctx.on_event is not None:
            try:
                await ctx.on_event(kind, data)
            except Exception as e:  # xabar berish xatosi asosiy jarayonni to'xtatmasin
                logger.warning(f"Hodisa yuborishda xato: {e}")

    async def _failover(self, from_role: str, reason: str, ctx: CallContext) -> bool:
        """Zaxira loyihaga o'tadi. Muvaffaqiyatli bo'lsa (yoki boshqa chaqiruv allaqachon o'tkazgan bo'lsa) True."""
        async with self._switch_lock:
            if self.role != from_role:
                return True
            if from_role == SECONDARY or not self._role_configured(SECONDARY):
                return False
            self._ready.clear()
            try:
                # Jarayondagi so'rovlar tugashini kutish (ee global holatga ega)
                async with self._inflight_cond:
                    try:
                        await asyncio.wait_for(
                            self._inflight_cond.wait_for(lambda: self._inflight == 0),
                            timeout=self.timeout_s + 5.0,
                        )
                    except TimeoutError:
                        logger.warning("Failover: jarayondagi soʻrovlar kutish muddati tugadi")
                async with self._init_lock:
                    try:
                        await asyncio.wait_for(
                            asyncio.to_thread(self._initializer, SECONDARY, int(self.timeout_s)),
                            timeout=self.timeout_s,
                        )
                    except Exception as e:
                        logger.warning(f"Zaxira GEE loyihasini initsializatsiya qilib boʻlmadi: {e}")
                        return False
                    self.role = SECONDARY
                    self._initialized_role = SECONDARY
                self.failover_happened = True
                logger.warning(f"Zaxira GEE loyihasiga oʻtildi (sabab: {reason})")
            finally:
                self._ready.set()
        await self._notify(ctx, "failover", {"reason": reason})
        return True

    # ------------------------------------------------------------------
    # Asosiy chaqiruv
    # ------------------------------------------------------------------
    def _backoff(self, attempt: int) -> float:
        base = C.GEE_BACKOFF_BASE_S * (2**attempt)
        return min(C.GEE_BACKOFF_MAX_S, base) + random.uniform(0.0, C.GEE_BACKOFF_BASE_S)

    async def call(
        self,
        fn: Callable[[], Any],
        *,
        ctx: CallContext,
        operation: str,
        purpose: str,
        dataset: str,
        request: str = "",
    ) -> Any:
        """Sinxron `fn` ni thread'da, semafor, timeout, qayta urinish va failover bilan bajaradi."""
        attempt = 0
        while True:
            await self._ready.wait()
            await self._ensure_initialized_safe(ctx)
            role = self.role
            start = time.perf_counter()
            kind: str | None = None
            error: BaseException | None = None
            result: Any = None

            async with self._sem:
                async with self._inflight_cond:
                    self._inflight += 1
                try:
                    result = await asyncio.wait_for(asyncio.to_thread(fn), timeout=self.timeout_s)
                except TimeoutError as e:
                    kind, error = ERR_TIMEOUT, e
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    kind, error = classify_error(e), e
                finally:
                    async with self._inflight_cond:
                        self._inflight -= 1
                        self._inflight_cond.notify_all()

            duration_ms = (time.perf_counter() - start) * 1000.0
            await record_api_call(
                run_id=ctx.run_id,
                service=f"gee_{role}",
                operation=operation,
                purpose=purpose,
                dataset=dataset,
                request=request,
                status="success" if kind is None else kind,
                duration_ms=duration_ms,
                bytes_count=result_size_bytes(result) if kind is None else 0,
                retries=attempt,
                failover=(role == SECONDARY),
                response="" if kind is None else "",
                error=None if error is None else (str(error) or type(error).__name__),
            )
            if kind is None:
                return result

            logger.warning(f"GEE xatosi [{operation}/{purpose}] ({kind}, urinish {attempt}): {error}")
            if kind == ERR_MEMORY:
                raise GEEMemoryLimitError()
            if kind == ERR_FATAL:
                raise GEEError(f"GEE soʻrovi bajarilmadi: {str(error)[:300]}")

            can_retry = kind in (ERR_TRANSIENT, ERR_TIMEOUT) and attempt < self.max_retries
            wants_failover = kind in (ERR_QUOTA, ERR_AUTH, ERR_TIMEOUT) or (
                kind == ERR_TRANSIENT and attempt >= self.max_retries
            )
            if wants_failover and await self._failover(role, kind, ctx):
                attempt = 0
                continue
            if can_retry:
                await self._sleep(self._backoff(attempt))
                attempt += 1
                continue
            if kind == ERR_TIMEOUT:
                raise GEETimeoutError()
            if kind == ERR_QUOTA:
                raise GEEQuotaError()
            if kind == ERR_AUTH:
                raise GEEError(
                    f"GEE loyihasiga ruxsat yoʻq: {str(error)[:300]}", code="GEE_AUTH_ERROR"
                )
            raise GEEError(f"GEE barcha urinishlardan soʻng javob bermadi: {str(error)[:300]}")

    async def _ensure_initialized_safe(self, ctx: CallContext) -> None:
        """Initsializatsiya xatosida (ruxsat/timeout) zaxira loyihaga o'tishga harakat qiladi."""
        try:
            await self._ensure_initialized(ctx)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            role = self.role
            kind = classify_error(e)
            logger.warning(f"GEE initsializatsiya xatosi ({role}): {e}")
            if kind in (ERR_AUTH, ERR_QUOTA, ERR_TIMEOUT, ERR_TRANSIENT) and await self._failover(
                role, f"init_{kind}", ctx
            ):
                return
            if isinstance(e, GEEError):
                raise
            raise GEEError(f"GEE loyihasiga ulanib boʻlmadi: {str(e)[:300]}") from e


gateway = GEEGateway()
