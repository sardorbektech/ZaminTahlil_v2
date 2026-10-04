"""Ketma-ket haqiqiy kuzatuvlar orasidagi o'zgarishlar (SIMPLE.md §7.5).

ΔNDVI, ΔNDWI, ΔNDMI, ΔNBR, ΔVV va sinflararo o'tishlar. Interpolatsiya qilingan kadrlar ishlatilmaydi.
"""

from typing import Any

import numpy as np

from backend.app.core.constants import CHANGE_TRANSITION_MIN_PCT, CLASS_LABELS_UZ, CLASS_UNKNOWN


def compute_delta_array(current: np.ndarray, previous: np.ndarray) -> np.ndarray:
    """Pikselma-piksel farq: Δ = joriy − oldingi. Birortasi NaN bo'lsa natija NaN."""
    with np.errstate(invalid="ignore"):
        return (current.astype(np.float32) - previous.astype(np.float32)).astype(np.float32)


def compute_class_transitions(
    current_classes: np.ndarray,
    previous_classes: np.ndarray,
    aoi_mask: np.ndarray | None = None,
    min_pct: float = CHANGE_TRANSITION_MIN_PCT,
) -> dict[str, Any]:
    """Ikki sana orasidagi sinf o'tishlari (ikkala sanada ham ma'lum bo'lgan piksellar bo'yicha).

    Natija: taqqoslangan piksellar soni, o'zgargan ulush va o'tishlar ro'yxati
    (har biri: dan/ga sinf, piksellar, umumiy taqqoslangan piksellardagi %).
    """
    valid = (current_classes != CLASS_UNKNOWN) & (previous_classes != CLASS_UNKNOWN)
    if aoi_mask is not None:
        valid &= aoi_mask.astype(bool)
    total = int(valid.sum())
    if total == 0:
        return {"compared_pixels": 0, "changed_pct": None, "transitions": []}

    prev_v = previous_classes[valid].astype(np.int32)
    curr_v = current_classes[valid].astype(np.int32)
    changed = prev_v != curr_v
    transitions: list[dict[str, Any]] = []
    if changed.any():
        codes = prev_v[changed] * 100 + curr_v[changed]
        uniq, counts = np.unique(codes, return_counts=True)
        for code, cnt in zip(uniq.tolist(), counts.tolist(), strict=True):
            pct = cnt / total * 100.0
            if pct < min_pct:
                continue
            f, t = code // 100, code % 100
            transitions.append(
                {
                    "from_code": f,
                    "from_label": CLASS_LABELS_UZ.get(f, "Nomaʼlum"),
                    "to_code": t,
                    "to_label": CLASS_LABELS_UZ.get(t, "Nomaʼlum"),
                    "pixel_count": cnt,
                    "pct": round(pct, 2),
                }
            )
    transitions.sort(key=lambda x: -x["pct"])
    return {
        "compared_pixels": total,
        "changed_pct": round(float(changed.sum()) / total * 100.0, 2),
        "transitions": transitions,
    }


def class_change_mask(current_classes: np.ndarray, previous_classes: np.ndarray) -> np.ndarray:
    """Sinf o'zgargan piksellar niqobi: 1 — o'zgargan, 0 — o'zgarmagan, NaN — taqqoslab bo'lmaydi."""
    valid = (current_classes != CLASS_UNKNOWN) & (previous_classes != CLASS_UNKNOWN)
    out = np.full(current_classes.shape, np.nan, dtype=np.float32)
    out[valid] = (current_classes[valid] != previous_classes[valid]).astype(np.float32)
    return out
