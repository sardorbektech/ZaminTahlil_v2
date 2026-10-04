"""Ilova istisnolari va xatoliklar tuzilmasi.

Barcha xatoliklar API'da {code, message_uz} shaklida qaytariladi.
"""

from typing import Any


class AppError(Exception):
    """Barcha maxsus ilova xatolarining asosi."""

    def __init__(self, code: str, message_uz: str, status_code: int = 400, details: Any = None):
        super().__init__(message_uz)
        self.code = code
        self.message_uz = message_uz
        self.status_code = status_code
        self.details = details

    def to_dict(self) -> dict[str, Any]:
        """Xatolikni JSON uchun mos lug'atga o'tkazadi."""
        res: dict[str, Any] = {"code": self.code, "message_uz": self.message_uz}
        if self.details is not None:
            res["details"] = self.details
        return res


class ConflictError(AppError):
    """Bir vaqtning o'zida ikkinchi vazifa boshlanganida yuzaga keladigan xato (409)."""

    def __init__(
        self,
        message_uz: str = "Hozirda boshqa rekognossirovka vazifasi bajarilmoqda.",
        code: str = "JOB_ALREADY_RUNNING",
    ):
        super().__init__(code=code, message_uz=message_uz, status_code=409)


class NotFoundError(AppError):
    """Resurs topilmaganda yuzaga keladigan xato (404)."""

    def __init__(self, message_uz: str = "Soʻralgan maʼlumot topilmadi."):
        super().__init__(code="NOT_FOUND", message_uz=message_uz, status_code=404)


class ValidationAppError(AppError):
    """So'rov parametrlari yaroqsiz (422)."""

    def __init__(self, message_uz: str, code: str = "VALIDATION_ERROR"):
        super().__init__(code=code, message_uz=message_uz, status_code=422)


class AOIValidationError(ValidationAppError):
    """Hudud geometriyasi yoki maydoni yaroqsiz bo'lganda (422)."""

    def __init__(self, message_uz: str = "Hudud maydoni yoki geometriyasi yaroqsiz."):
        super().__init__(message_uz=message_uz, code="INVALID_AOI")


class GEEError(AppError):
    """Google Earth Engine bilan bog'liq xatoliklar."""

    def __init__(
        self,
        message_uz: str = "Google Earth Engine maʼlumotlarini olishda xatolik yuz berdi.",
        code: str = "GEE_ERROR",
    ):
        super().__init__(code=code, message_uz=message_uz, status_code=502)


class GEENotConfiguredError(GEEError):
    """GEE loyihasi yoki kalit fayli sozlanmagan."""

    def __init__(self) -> None:
        super().__init__(
            "GEE loyihasi sozlanmagan: .env faylida GEE_PROJECT_PRIMARY va "
            "GEE_KEY_FILE_PRIMARY koʻrsatilishi kerak.",
            code="GEE_NOT_CONFIGURED",
        )


class GEETimeoutError(GEEError):
    """GEE so'rovi vaqt chegarasidan oshib ketganda."""

    def __init__(self, message_uz: str = "GEE soʻrovi belgilangan vaqt ichida javob bermadi."):
        super().__init__(message_uz=message_uz, code="GEE_TIMEOUT")


class GEEQuotaError(GEEError):
    """GEE kvotasi yoki so'rovlar limiti tugaganda."""

    def __init__(self, message_uz: str = "GEE loyihasi kvotasi yoki ruxsat limiti tugadi."):
        super().__init__(message_uz=message_uz, code="GEE_QUOTA_EXCEEDED")


class GEEMemoryLimitError(GEEError):
    """GEE "User memory limit exceeded" — so'rovni kichikroq bo'laklarga bo'lish kerak."""

    def __init__(self) -> None:
        super().__init__("GEE xotira chegarasi oshdi.", code="GEE_MEMORY_LIMIT")


class AIReportError(AppError):
    """AI hisobotini yaratib bo'lmadi (qayta urinish mumkin)."""

    def __init__(self, message_uz: str, code: str = "AI_REPORT_FAILED"):
        super().__init__(code=code, message_uz=message_uz, status_code=502)
