"""API foydalanish nazorati (/api/v1/usage)."""

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.security import CurrentUser, current_user
from backend.app.core.errors import NotFoundError
from backend.app.db.models import RunModel
from backend.app.db.session import get_db
from backend.app.usage.tracker import get_run_usage_summary

router = APIRouter(prefix="/usage", tags=["Nazorat"])


@router.get("/runs/{run_id}")
async def get_usage_for_run(
    run_id: int, db: AsyncSession = Depends(get_db), user: CurrentUser = Depends(current_user)
) -> dict[str, Any]:
    """Run bo'yicha tashqi chaqiruvlar: Markdown xulosa (xizmat/maqsad kesimida) va chaqiruvlar ro'yxati."""
    run = await db.get(RunModel, run_id)
    if run is None or run.user_id != user.id:
        raise NotFoundError(f"Maydon #{run_id} topilmadi.")
    return await get_run_usage_summary(run_id)
