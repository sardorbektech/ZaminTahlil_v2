"""Google Earth Engine (GEE) autentifikatsiyasi va loyiha almashuvi moduli."""

import asyncio
from pathlib import Path

import ee
from google.oauth2 import service_account

from backend.app.core.config import settings
from backend.app.core.errors import GEEError
from backend.app.core.telemetry import logger

_ee_init_lock = asyncio.Lock()
_current_project_role: str = "primary"  # "primary" yoki "secondary"
_is_initialized: bool = False


def _get_credentials_for_role(role: str) -> tuple[str, str]:
    """Berilgan rol (primary/secondary) uchun loyiha nomi va kalit faylini qaytaradi."""
    if role == "secondary":
        return settings.gee_project_secondary, settings.gee_key_file_secondary
    return settings.gee_project_primary, settings.gee_key_file_primary


def init_ee_sync(role: str = "primary") -> bool:
    """Sinxron Earth Engine initsializatsiyasi."""
    global _current_project_role, _is_initialized
    project, key_file = _get_credentials_for_role(role)

    try:
        if key_file and Path(key_file).exists():
            creds = service_account.Credentials.from_service_account_file(
                key_file, scopes=["https://www.googleapis.com/auth/earthengine"]
            )
            ee.Initialize(credentials=creds, project=project or None)
        else:
            ee.Initialize(project=project or None)

        _current_project_role = role
        _is_initialized = True
        logger.info(f"GEE muvaffaqiyatli initsializatsiya qilindi. Loyiha: {project or 'default'} ({role})")
        return True
    except Exception as e:
        logger.warning(f"GEE initsializatsiya xatosi ({role}): {e}")
        return False


async def ensure_ee_initialized(force_role: str | None = None) -> None:
    """Asinxron ravishda GEE initsializatsiyasini tekshiradi yoki zaxiraga o'tkazadi."""
    global _current_project_role, _is_initialized

    async with _ee_init_lock:
        target_role = force_role or _current_project_role
        if _is_initialized and not force_role and target_role == _current_project_role:
            return

        success = await asyncio.to_thread(init_ee_sync, target_role)
        if not success:
            if target_role == "primary" and settings.gee_project_secondary:
                logger.warning("Asosiy GEE ulanmadi, zaxira loyihaga o'tilmoqda...")
                sec_success = await asyncio.to_thread(init_ee_sync, "secondary")
                if not sec_success:
                    raise GEEError("GEE asosiy va zaxira loyihalariga ulanib bo'lmadi.")
            else:
                raise GEEError(f"GEE loyihasiga ({target_role}) ulanib bo'lmadi.")


async def switch_to_secondary_project() -> bool:
    """Kvota yoki xatolikda zaxira GEE loyihasiga o'tadi."""
    global _current_project_role
    if not settings.gee_project_secondary:
        logger.warning("Zaxira GEE loyihasi sozlanmagan!")
        return False

    async with _ee_init_lock:
        if _current_project_role == "secondary":
            return False  # Allaqachon zaxirada

        logger.info("Zaxira GEE loyihasiga o'tilmoqda...")
        success = await asyncio.to_thread(init_ee_sync, "secondary")
        return success


def get_current_project_role() -> str:
    """Hozirgi faol GEE loyihasi rolini (primary yoki secondary) qaytaradi."""
    return _current_project_role
