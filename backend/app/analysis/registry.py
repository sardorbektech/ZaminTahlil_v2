"""Analizatorlar registri (Registry).

Quvur (pipeline) analizatorlarni to'g'ridan-to'g'ri import qilmaydi,
balki ushbu registrdan nomi bo'yicha oladi.
"""

from backend.app.analysis.interface import Analyzer

_ANALYZERS: dict[str, Analyzer] = {}


def register_analyzer(analyzer: Analyzer) -> None:
    """Yangi analizatorni registrga kiritadi."""
    _ANALYZERS[analyzer.name] = analyzer


def get_analyzer(name: str) -> Analyzer:
    """Nomi bo'yicha analizatorni qaytaradi.

    Raises:
        KeyError: Agar analizator topilmasa.
    """
    if name not in _ANALYZERS:
        raise KeyError(f"Analizator topilmadi: {name}")
    return _ANALYZERS[name]


def list_analyzers() -> list[str]:
    """Ro'yxatdan o'tgan barcha analizatorlar nomini qaytaradi."""
    return list(_ANALYZERS.keys())
