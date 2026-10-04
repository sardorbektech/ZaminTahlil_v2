"""Oddiy username + parol bilan kirish (JWT yoki token yo'q).

- Brauzer har bir so'rovda `Authorization: Basic base64(username:parol)` yuboradi (UTF-8).
- Parollar PBKDF2-HMAC-SHA256 (tuz bilan) xeshi sifatida saqlanadi; ochiq parol hech qayerda saqlanmaydi.
- POST /auth/login: foydalanuvchi bo'lsa — parol tekshiriladi; bo'lmasa — yangisi yaratiladi.
- Boshqa endpointlar foydalanuvchini yaratmaydi: topilmasa yoki parol mos kelmasa — 401.
"""

import base64
import hashlib
import hmac
import os
import unicodedata
from collections import OrderedDict
from dataclasses import dataclass

from fastapi import Depends, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core import constants as C
from backend.app.core.errors import AppError
from backend.app.core.time import now_ts
from backend.app.db.models import UserModel
from backend.app.db.session import get_db

_CACHE_MAX = 512
# (tuz, sha256(parol)) -> PBKDF2 natijasi. Kalitda tuz bor: baza qayta yaratilsa ham eski kesh noto'g'ri mos kelmaydi
_verified: "OrderedDict[tuple[bytes, bytes, int], bytes]" = OrderedDict()


class AuthError(AppError):
    """Kirish xatosi (401)."""

    def __init__(self, message_uz: str = "Kirish talab qilinadi.", code: str = "AUTH_REQUIRED"):
        super().__init__(code=code, message_uz=message_uz, status_code=401)


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str


def normalize_username(raw: str) -> str:
    """Username: bosh/oxiridagi bo'shliqlar olinadi, Unicode NFC. Kamida 1 belgi."""
    u = unicodedata.normalize("NFC", (raw or "").strip())
    if not u:
        raise AppError("INVALID_USERNAME", "Username kamida 1 ta belgidan iborat boʻlishi kerak.", 422)
    if len(u) > C.USERNAME_MAX_LEN or ":" in u:
        raise AppError("INVALID_USERNAME", f"Username {C.USERNAME_MAX_LEN} belgidan oshmasin va «:» belgisisiz boʻlsin.", 422)
    return u


def validate_password(raw: str) -> str:
    if raw is None or len(raw) < 1:
        raise AppError("INVALID_PASSWORD", "Parol kamida 1 ta belgidan iborat boʻlishi kerak.", 422)
    if len(raw) > C.PASSWORD_MAX_LEN:
        raise AppError("INVALID_PASSWORD", f"Parol {C.PASSWORD_MAX_LEN} belgidan oshmasin.", 422)
    return raw


def hash_password(password: str, salt: bytes, iterations: int = C.PBKDF2_ITERATIONS) -> bytes:
    """PBKDF2-HMAC-SHA256, 32 bayt."""
    key = (salt, hashlib.sha256(password.encode("utf-8")).digest(), iterations)
    if key in _verified:
        _verified.move_to_end(key)
        return _verified[key]
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, iterations, dklen=32)
    _verified[key] = dk
    if len(_verified) > _CACHE_MAX:
        _verified.popitem(last=False)
    return dk


def verify_password(user: UserModel, password: str) -> bool:
    return hmac.compare_digest(hash_password(password, user.salt, user.iterations), user.password_hash)


def parse_basic(header: str | None) -> tuple[str, str] | None:
    """`Basic base64(username:parol)` sarlavhasini UTF-8 bo'yicha ochadi."""
    if not header or not header.lower().startswith("basic "):
        return None
    try:
        raw = base64.b64decode(header[6:].strip(), validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    if ":" not in raw:
        return None
    user, pw = raw.split(":", 1)
    return user, pw


async def login_or_create(db: AsyncSession, username: str, password: str) -> tuple[CurrentUser, bool]:
    """Mavjud foydalanuvchini tekshiradi yoki yangisini yaratadi. (foydalanuvchi, yaratildimi)."""
    username = normalize_username(username)
    password = validate_password(password)
    user = (await db.execute(select(UserModel).where(UserModel.username == username))).scalars().first()
    if user is not None:
        if not verify_password(user, password):
            raise AuthError("Username yoki parol notoʻgʻri.", code="AUTH_FAILED")
        return CurrentUser(user.id, user.username), False
    salt = os.urandom(16)
    user = UserModel(
        username=username,
        password_hash=hash_password(password, salt),
        salt=salt,
        iterations=C.PBKDF2_ITERATIONS,
        created_at=now_ts(),
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()  # parallel so'rov yaratib qo'ygan bo'lsa — oddiy kirish sifatida tekshiramiz
        return await login_or_create(db, username, password)
    return CurrentUser(user.id, user.username), True


async def current_user(request: Request, db: AsyncSession = Depends(get_db)) -> CurrentUser:
    """Har bir himoyalangan endpoint uchun: Basic sarlavhadan foydalanuvchini aniqlaydi."""
    creds = parse_basic(request.headers.get("authorization"))
    if creds is None:
        raise AuthError()
    username = unicodedata.normalize("NFC", creds[0].strip())
    user = (await db.execute(select(UserModel).where(UserModel.username == username))).scalars().first()
    if user is None or not verify_password(user, creds[1]):
        raise AuthError("Username yoki parol notoʻgʻri.", code="AUTH_FAILED")
    return CurrentUser(user.id, user.username)
