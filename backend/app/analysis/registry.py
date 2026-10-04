"""Analizatorlar registri.

Quvur analizatorlarni to'g'ridan-to'g'ri import qilmaydi — faqat shu registrdan nomi bo'yicha oladi.
"""

from backend.app.analysis.interface import Analyzer

_ANALYZERS: dict[str, Analyzer] = {}


def register_analyzer(analyzer: Analyzer) -> None:
    """Analizatorni registrga kiritadi (bir xil nom bo'lsa almashtiradi)."""
    _ANALYZERS[analyzer.name] = analyzer


def get_analyzer(name: str) -> Analyzer:
    """Nomi bo'yicha analizatorni qaytaradi.

    Raises:
        KeyError: analizator topilmasa.
    """
    if not _ANALYZERS:
        from backend.app.analysis.analyzers import init_all_analyzers

        init_all_analyzers()
    if name not in _ANALYZERS:
        raise KeyError(f"Analizator topilmadi: {name}")
    return _ANALYZERS[name]


def list_analyzers() -> dict[str, str]:
    """Ro'yxatdan o'tgan analizatorlar: {nom: versiya}."""
    return {k: v.version for k, v in _ANALYZERS.items()}


def _ensure() -> None:
    if not _ANALYZERS:
        from backend.app.analysis.analyzers import init_all_analyzers

        init_all_analyzers()


def analyzers_for(stage: str, slot: str) -> list[Analyzer]:
    """Berilgan bosqich va slot uchun analizatorlar (masalan, S2 kuzatuvidagi qo'shimcha ML qatlamlari)."""
    _ensure()
    return [a for a in _ANALYZERS.values() if getattr(a, "stage", None) == stage and getattr(a, "slot", None) == slot]


def landcover_choices() -> list[dict[str, str]]:
    """Yer qoplami slotiga qo'yish mumkin bo'lgan analizatorlar (sozlamalar uchun)."""
    _ensure()
    return [
        {"name": a.name, "version": a.version, "method": getattr(a, "method", "rules")}
        for a in _ANALYZERS.values()
        if getattr(a, "slot", None) == "landcover"
    ]


def unregister_analyzer(name: str) -> None:
    """Testlar uchun: analizatorni registrdan olib tashlash."""
    _ANALYZERS.pop(name, None)
