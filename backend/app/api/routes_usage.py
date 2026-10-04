"""API foydalanish nazorati (/api/v1/usage)."""

from typing import Any

from fastapi import APIRouter

from backend.app.usage.tracker import get_run_usage_summary

router = APIRouter(prefix="/usage", tags=["Nazorat"])


@router.get("/runs/{run_id}")
async def get_usage_for_run(run_id: int) -> dict[str, Any]:
    """Run bo'yicha tashqi chaqiruvlar: Markdown xulosa (xizmat/maqsad kesimida) va chaqiruvlar ro'yxati."""
    return await get_run_usage_summary(run_id)
