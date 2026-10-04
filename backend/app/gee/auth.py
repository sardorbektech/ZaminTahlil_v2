"""GEE autentifikatsiyasi: asosiy va zaxira loyihalar uchun `ee` ni initsializatsiya qilish.

`ee` global holatga ega, shuning uchun loyiha almashtirish faqat gateway'dagi qulf ostida
va barcha jarayondagi so'rovlar tugagandan keyin bajariladi (gateway.py).
"""

from backend.app.core.config import settings
from backend.app.core.errors import GEENotConfiguredError

PRIMARY = "primary"
SECONDARY = "secondary"


def project_for_role(role: str) -> tuple[str, str]:
    """Rol uchun (loyiha ID, kalit fayli yo'li) juftligini qaytaradi."""
    if role == SECONDARY:
        return settings.gee_project_secondary, settings.gee_key_file_secondary
    return settings.gee_project_primary, settings.gee_key_file_primary


def is_role_configured(role: str) -> bool:
    """Rol uchun loyiha ID va mavjud kalit fayli ko'rsatilganmi."""
    project, key_file = project_for_role(role)
    return bool(project and key_file and settings.resolve_path(key_file).exists())


def init_ee_for_role(role: str, timeout_s: int) -> None:
    """Sinxron: `ee` ni berilgan rol loyihasi bilan initsializatsiya qiladi (thread ichida chaqiriladi)."""
    import ee
    from google.oauth2 import service_account

    if not is_role_configured(role):
        raise GEENotConfiguredError()
    project, key_file = project_for_role(role)
    creds = service_account.Credentials.from_service_account_file(
        str(settings.resolve_path(key_file)),
        scopes=["https://www.googleapis.com/auth/earthengine"],
    )
    ee.Initialize(credentials=creds, project=project)
    # HTTP so'rovlari ham shu muddatdan keyin uziladi
    ee.data.setDeadline(int(timeout_s * 1000))
