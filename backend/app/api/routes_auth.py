"""Kirish (/api/v1/auth). Ro'yxatdan o'tish yo'q: username topilmasa — yangi foydalanuvchi yaratiladi."""

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.auth.security import CurrentUser, current_user, login_or_create
from backend.app.db.session import get_db

router = APIRouter(prefix="/auth", tags=["Kirish"])


class LoginSchema(BaseModel):
    username: str
    password: str


@router.post("/login")
async def login(payload: LoginSchema, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """Username + parol: mos kelsa kiradi, username yo'q bo'lsa yangisi yaratiladi, parol xato bo'lsa — 401."""
    user, created = await login_or_create(db, payload.username, payload.password)
    return {
        "user": {"id": user.id, "username": user.username},
        "created": created,
        "message_uz": "Yangi foydalanuvchi yaratildi" if created else "Xush kelibsiz",
    }


@router.get("/me")
async def me(user: CurrentUser = Depends(current_user)) -> dict[str, Any]:
    return {"user": {"id": user.id, "username": user.username}}
