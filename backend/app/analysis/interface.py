"""Analyzer interfeysi va kiruvchi/chiquvchi ma'lumot modellari (SIMPLE.md §7.1).

Har bir tahlil qadami shu interfeys ortida turadi va kelajakda AI modeli bilan almashtirilishi mumkin.
"""

from dataclasses import dataclass, field
from typing import Any, Protocol

import numpy as np


@dataclass
class AnalyzerInput:
    """Analizatorga uzatiladigan massivlar va metama'lumotlar."""

    arrays: dict[str, np.ndarray]  # masalan: {"B2": arr, "B4": arr, "B8": arr, ...}
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
    """Barcha tahlil modullari uchun umumiy protokol."""

    name: str  # masalan: "ndvi", "landcover"
    version: str  # masalan: "rules-1.0"

    def run(self, data: AnalyzerInput) -> AnalyzerOutput:  # qatlamlar, statistika, ishonchlilik
        ...
