"""Kuzatuv sanalari bo'yicha dinamik o'zgarishlarni aniqlash moduli.

Ketma-ket haqiqiy kuzatuvlar orasidagi farqlar (ΔNDVI, ΔNDWI, ΔNDMI, ΔVV, ΔSM)
va sinflararo o'tishlar (class transitions) matritsasi.
"""

from typing import Any

import numpy as np

from backend.app.core.constants import CLASS_LABELS_UZ


def compute_delta_array(current: np.ndarray, previous: np.ndarray) -> np.ndarray:
    """Ikkita kuzatuv orasidagi pikselma-piksel farqni (Δ = joriy - oldingi) hisoblaydi."""
    with np.errstate(invalid="ignore"):
        delta = current - previous
    return delta.astype(np.float32)


def compute_class_transitions(
    current_classes: np.ndarray, previous_classes: np.ndarray
) -> list[dict[str, Any]]:
    """Sinflar o'rtasidagi o'zgarishlarni (masalan: Ochiq tuproq -> Ekin) aniqlaydi."""
    valid_mask = (current_classes > 0) & (previous_classes > 0)
    transitions: list[dict[str, Any]] = []

    curr_valid = current_classes[valid_mask]
    prev_valid = previous_classes[valid_mask]

    changed_mask = curr_valid != prev_valid
    if not np.any(changed_mask):
        return transitions

    unique_pairs, counts = np.unique(
        np.column_stack((prev_valid[changed_mask], curr_valid[changed_mask])),
        axis=0,
        return_counts=True,
    )

    total_valid = float(np.sum(valid_mask))
    for (from_cls, to_cls), count in zip(unique_pairs, counts, strict=False):
        pct = (float(count) / total_valid) * 100.0 if total_valid > 0 else 0.0
        if pct >= 0.1:  # Kamida 0.1% hudud o'zgargan bo'lsa
            transitions.append({
                "from_code": int(from_cls),
                "from_label": CLASS_LABELS_UZ.get(int(from_cls), "Nomaʼlum"),
                "to_code": int(to_cls),
                "to_label": CLASS_LABELS_UZ.get(int(to_cls), "Nomaʼlum"),
                "pixel_count": int(count),
                "pct": round(pct, 2),
            })

    transitions.sort(key=lambda x: x["pct"], reverse=True)
    return transitions
