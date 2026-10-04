"""API foydalanish nazorati yo'nalishi (/api/v1/usage)."""

from typing import Any

from fastapi import APIRouter

from backend.app.usage.tracker import get_run_usage_summary

router = APIRouter(prefix="/usage", tags=["Nazorat"])


@router.get("/runs/{run_id}")
async def get_usage_for_run(run_id: int) -> dict[str, Any]:
    """Berilgan vazifa (run_id) bo'yicha API foydalanish xulosasini qaytaradi."""
    return await get_run_usage_summary(run_id)
