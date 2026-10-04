"""Sifat baholash va o'zgarishlar tahlili testlari."""

import numpy as np

from backend.app.analysis.changes import compute_class_transitions
from backend.app.analysis.quality import cross_check_ndvi, evaluate_layer_quality


def test_quality_evaluation():
    arr = np.array([[0.5, np.nan], [0.8, 0.2]], dtype=np.float32)
    # 4 tadan 3 tasi yaroqli = 75%
    res = evaluate_layer_quality(arr)
    assert res["valid_pct"] == 75.0
    assert not res["is_low_confidence"]


def test_ndvi_cross_check():
    s2 = np.array([0.5, 0.6, 0.7], dtype=np.float32)
    ls = np.array([0.52, 0.58, 0.69], dtype=np.float32)

    res = cross_check_ndvi(s2, ls, time_diff_days=1.5)
    assert res["available"] is True
    assert res["is_consistent"] is True


def test_class_transitions():
    curr = np.array([1, 4, 3], dtype=np.uint8)
    prev = np.array([1, 6, 3], dtype=np.uint8)

    transitions = compute_class_transitions(curr, prev)
    assert len(transitions) == 1
    # 6 (Ochiq tuproq) -> 4 (Ekin / dala)
    assert transitions[0]["from_code"] == 6
    assert transitions[0]["to_code"] == 4
