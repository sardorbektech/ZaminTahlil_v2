"""Bekor qilish (cancellation) va tozalash testlari."""

import asyncio

import pytest

from backend.app.core.config import RUNS_DIR
from backend.app.pipeline.cancellation import (
    cancel_run,
    is_cancellation_requested,
    register_active_run,
)


@pytest.mark.asyncio
async def test_cancellation_cleans_resources():
    test_run_id = 99999
    run_folder = RUNS_DIR / str(test_run_id)
    run_folder.mkdir(parents=True, exist_ok=True)
    dummy_file = run_folder / "test.png"
    dummy_file.write_text("test")

    # Soxta task yaratish
    async def dummy_work():
        await asyncio.sleep(10)

    task = asyncio.create_task(dummy_work())
    register_active_run(test_run_id, task)

    # Bekor qilish
    assert not is_cancellation_requested(test_run_id)
    await cancel_run(test_run_id)

    # Tekshirish
    assert task.cancelled() or task.done()
    assert not run_folder.exists()
