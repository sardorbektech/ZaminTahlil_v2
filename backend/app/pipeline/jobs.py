"""Vazifalar boshqaruvchisi: bir vaqtda bitta run, SSE hodisalari va bekor qilish.

- Faol run bo'lsa yangi run 409 bilan rad etiladi (SIMPLE.md §4.2).
- Hodisalar tarixi saqlanadi: sahifa qayta yuklanganda SSE oqimi boshidan takrorlanadi.
- Bekor qilish (§6): vazifa va HTTP kutishlari to'xtatiladi, massivlar tashlanadi, gc.collect(),
  run katalogi va DB qatorlari o'chiriladi, `cancelled` hodisasi yuboriladi — ~2 soniya ichida.
"""

import asyncio
import gc
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import delete

from backend.app.core.constants import CANCEL_WAIT_S
from backend.app.core.errors import ConflictError
from backend.app.core.telemetry import logger
from backend.app.core.time import fmt_local, now_ts
from backend.app.db import session as db
from backend.app.db.models import RunModel
from backend.app.pipeline.storage import delete_run_dir

TOTAL_STAGES = 10
TERMINAL_EVENTS = ("done", "cancelled", "error", "duplicate")


@dataclass
class Job:
    """Bitta faol (yoki yaqinda tugagan) run holati."""

    run_id: int
    task: asyncio.Task[Any] | None = None
    events: list[dict[str, Any]] = field(default_factory=list)
    subscribers: list[asyncio.Queue[dict[str, Any]]] = field(default_factory=list)
    cancel_requested: bool = False
    finished: bool = False
    stage: int = 0
    progress: float = 0.0

    def emit(
        self,
        type_: str,
        message_uz: str,
        stage: int | None = None,
        progress: float | None = None,
        data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Hodisani tarixga yozadi va barcha obunachilarga yuboradi."""
        if stage is not None:
            self.stage = stage
        if progress is not None:
            self.progress = max(self.progress, min(1.0, progress))
        ts = now_ts()
        ev = {
            "seq": len(self.events),
            "type": type_,
            "run_id": self.run_id,
            "stage": self.stage,
            "total_stages": TOTAL_STAGES,
            "progress": round(self.progress, 4),
            "message_uz": message_uz,
            "data": data or {},
            "ts": ts,
            "ts_local": fmt_local(ts),
        }
        self.events.append(ev)
        if type_ in TERMINAL_EVENTS:
            self.finished = True
        for q in list(self.subscribers):
            q.put_nowait(ev)
        return ev


async def delete_run_records(run_id: int) -> None:
    """Run va unga bog'liq barcha DB qatorlarini o'chiradi (FK CASCADE)."""
    async with db.session_scope() as s:
        await s.execute(delete(RunModel).where(RunModel.id == run_id))
        await s.commit()


class JobManager:
    """Yagona faol vazifani boshqaruvchi."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.active: Job | None = None
        self.last: Job | None = None

    def active_run_id(self) -> int | None:
        if self.active is not None and not self.active.finished:
            return self.active.run_id
        return None

    def get_job(self, run_id: int) -> Job | None:
        for j in (self.active, self.last):
            if j is not None and j.run_id == run_id:
                return j
        return None

    async def start(
        self,
        create_run: Callable[[], Awaitable[int]],
        runner: Callable[[Job], Awaitable[None]],
    ) -> Job:
        """Yangi vazifani boshlaydi. `create_run` DB qatorini yaratadi, `runner` quvurni bajaradi."""
        async with self._lock:
            if self.active_run_id() is not None:
                raise ConflictError()
            run_id = await create_run()
            job = Job(run_id=run_id)
            self.last, self.active = self.active, job
            job.task = asyncio.create_task(self._wrap(job, runner), name=f"recon-{run_id}")
            return job

    async def _wrap(self, job: Job, runner: Callable[[Job], Awaitable[None]]) -> None:
        try:
            await runner(job)
        except asyncio.CancelledError:
            # cancel() tozalashni o'zi bajaradi; bu yerda faqat ehtiyot chorasi
            if not job.cancel_requested:
                await self._cleanup(job.run_id)
                job.emit("cancelled", "Vazifa toʻxtatildi")
        finally:
            gc.collect()
            if self.active is job and job.finished:
                self.last, self.active = job, None

    async def _cleanup(self, run_id: int) -> None:
        delete_run_dir(run_id)
        try:
            await delete_run_records(run_id)
        except Exception as e:
            logger.warning(f"Run #{run_id} DB qatorlarini oʻchirishda xato: {e}")
        gc.collect()

    async def cancel(self, run_id: int) -> bool:
        """Faol vazifani to'xtatadi va tozalaydi. Vazifa faol bo'lmasa False."""
        job = self.active
        if job is None or job.run_id != run_id or job.finished:
            return False
        job.cancel_requested = True
        task = job.task
        if task is not None and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), timeout=CANCEL_WAIT_S)
            except (asyncio.CancelledError, TimeoutError, Exception):
                pass
        await self._cleanup(run_id)
        job.emit("cancelled", "Vazifa toʻxtatildi, vaqtinchalik fayllar oʻchirildi")
        if self.active is job:
            self.last, self.active = job, None
        logger.info(f"Run #{run_id} bekor qilindi va tozalandi")
        return True

    def subscribe(self, job: Job) -> asyncio.Queue[dict[str, Any]]:
        """Obuna: avval tarixdagi barcha hodisalar, keyin jonli hodisalar."""
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        for ev in job.events:
            q.put_nowait(ev)
        job.subscribers.append(q)
        return q

    @staticmethod
    def unsubscribe(job: Job, q: asyncio.Queue[dict[str, Any]]) -> None:
        if q in job.subscribers:
            job.subscribers.remove(q)

    async def shutdown(self) -> None:
        """Server to'xtaganda faol vazifani bekor qiladi."""
        if self.active is not None and not self.active.finished:
            await self.cancel(self.active.run_id)


job_manager = JobManager()
