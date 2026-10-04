"""Analyzer interfeysi va kiruvchi/chiquvchi ma'lumot modellari (SIMPLE.md §7.1).

Har bir tahlil qadami shu interfeys ortida turadi: qoidaviy formula, klassik ML (piksel bo'yicha)
yoki computer vision (rasm bo'yicha) modeli bir xil tarzda ulanadi va registrdan nomi bilan olinadi.
"""

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

import numpy as np

# Usul: qatlam qanday hosil qilinganini UI va API ko'rsatadi
Method = Literal["rules", "classic_ml", "cv"]
# Qaysi kuzatuv turida ishga tushadi
Stage = Literal["s2_observation", "s1_observation", "landsat_observation", "terrain", "soil", "change"]
# Slot: "landcover" — asosiy tasnifni almashtiradi; "extra" — qo'shimcha qatlamlar beradi; None — ichki
Slot = Literal["landcover", "extra"] | None


@dataclass
class AnalyzerInput:
    """Analizatorga uzatiladigan massivlar va metama'lumotlar."""

    arrays: dict[str, np.ndarray]  # masalan: {"B2": arr, "ndvi": arr, "vv": arr, ...}
    pixel_size_m: float = 10.0  # pikselning yerdagi o'lchami (metr)
    aoi_mask: np.ndarray | None = None  # True — AOI ichida; statistika shu bo'yicha
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class AnalyzerOutput:
    """Analizator natijasi: qatlamlar, statistika va ishonchlilik."""

    layers: dict[str, np.ndarray]
    stats: dict[str, dict[str, float | int | None]]
    confidence: np.ndarray | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class Analyzer(Protocol):
    """Barcha tahlil modullari uchun umumiy protokol.

    Majburiy: name, version, run(). Ixtiyoriy atributlar (bo'lmasa standart qiymat olinadi):
      method: "rules" | "classic_ml" | "cv"   (standart: "rules")
      stage:  qaysi kuzatuvda ishlashi        (standart: None — faqat quvur o'zi chaqiradi)
      slot:   "landcover" | "extra" | None    (standart: None)
      inputs: kerakli kirish massivlari nomlari (masalan, ["B4", "B8", "ndvi", "vv"])
      layer_specs: chiqish qatlamlari tavsifi {nom: LayerSpec} — render.register_layer_spec orqali qo'shiladi
    """

    name: str  # masalan: "ndvi", "landcover"
    version: str  # masalan: "rules-1.0"

    def run(self, data: AnalyzerInput) -> AnalyzerOutput:  # qatlamlar, statistika, ishonchlilik
        ...


def analyzer_method(a: Any) -> str:
    return getattr(a, "method", "rules")


def producer_of(a: Any) -> str:
    """Qatlamni kim yaratgani: "usul:nom:versiya" (DB va API uchun)."""
    return f"{analyzer_method(a)}:{a.name}:{a.version}"
