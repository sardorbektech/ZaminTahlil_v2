"""Klassik ML va computer vision modellari uchun kengaytma nuqtasi.

Yangi model qo'shish:
    1. `PixelModelAnalyzer` (klassik ML: har bir piksel = belgi vektori) yoki
       `ImageModelAnalyzer` (CV: kanallar × H × W tensor) dan meros oling.
    2. `inputs`, `output_specs` va `predict_*` ni yozing (modelni `load()` da yuklang).
    3. `register_model(MyModel())` ni chaqiring (masalan, `analysis/models/<nom>.py` ichida va
       uni `ENABLED_MODELS` ga qo'shing).
    4. Asosiy yer qoplami tasnifini almashtirish uchun `slot = "landcover"` qiling va
       sozlamalarda `landcover_analyzer` ni model nomiga o'rnating; qo'shimcha qatlamlar uchun `slot = "extra"`.
Quvur, API va frontend yangi qatlamni avtomatik ko'rsatadi (nomi, afsonasi, "ML"/"CV" belgisi bilan).
"""

from backend.app.analysis.models.base import (  # noqa: F401
    ImageModelAnalyzer,
    PixelModelAnalyzer,
    register_model,
)
from backend.app.analysis.models.features import build_feature_stack, unflatten  # noqa: F401

# Ilova ishga tushganda yuklanadigan model modullari (import yo'li). Hozircha bo'sh.
ENABLED_MODELS: list[str] = []
