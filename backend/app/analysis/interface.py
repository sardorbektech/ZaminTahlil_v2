"""Analyzer interfeysi va kiruvchi/chiquvchi ma'lumotlar modellari."""

from dataclasses import dataclass
from typing import Any, Protocol

import numpy as np


@dataclass
class AnalyzerInput:
    """Analizatorga uzatiladigan massivlar va metama'lumotlar to'plami."""

    arrays: dict[str, np.ndarray]  # Masalan: {"B2": arr, "B3": arr, "B4": arr, "B8": arr, ...}
    pixel_size_m: float = 10.0
    extra: dict[str, Any] | None = None


@dataclass
class AnalyzerOutput:
    """Analizator natijasi: qatlamlar, statistika va ishonchlilik bahosi."""

    layers: dict[str, np.ndarray]  # Masalan: {"ndvi": arr, "confidence": arr}
    stats: dict[str, dict[str, float]]  # {"ndvi": {"mean": 0.45, "min": -0.2, ...}}
    metadata: dict[str, Any] | None = None


class Analyzer(Protocol):
    """Barcha tahlil modullari uchun umumiy protokol."""

    name: str  # masalan: "indices", "sar", "landcover"
    version: str  # masalan: "rules-1.0"

    def run(self, data: AnalyzerInput) -> AnalyzerOutput:
        """Tahlilni sof hisoblash orqali bajaradi."""
        ...
