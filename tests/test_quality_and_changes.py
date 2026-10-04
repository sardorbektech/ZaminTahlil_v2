"""Sifat bayroqlari (§7.6), S2–Landsat taqqoslash, o'zgarishlar (§7.5)."""

import numpy as np

from backend.app.analysis.analyzers import calc_stats
from backend.app.analysis.changes import (
    class_change_mask,
    compute_class_transitions,
    compute_delta_array,
)
from backend.app.analysis.quality import cross_check_ndvi, evaluate_layer_quality, quality_flag_for
from backend.app.db.enums import QualityFlag


def test_quality_flags_thresholds():
    assert quality_flag_for(0.0, None) == QualityFlag.NO_DATA
    assert quality_flag_for(29.99, 0.0) == QualityFlag.LOW_CONFIDENCE
    assert quality_flag_for(30.0, 0.0) == QualityFlag.GOOD
    assert quality_flag_for(35.0, 65.0) == QualityFlag.HIGH_CLOUD


def test_layer_quality_inside_aoi_only():
    arr = np.array([[0.5, np.nan], [np.nan, np.nan]], dtype=np.float32)
    aoi = np.array([[True, True], [False, False]])
    cloud = np.array([[False, True], [True, True]])
    q = evaluate_layer_quality(arr, aoi, cloud)
    assert q["valid_pct"] == 50.0 and q["cloud_masked_pct"] == 50.0
    assert q["quality_flag"] == QualityFlag.GOOD
    q2 = evaluate_layer_quality(np.full((10, 10), np.nan, np.float32))
    assert q2["quality_flag"] == QualityFlag.NO_DATA and q2["is_low_confidence"]
    low = np.full((10, 10), np.nan, np.float32)
    low[0, :2] = 1.0
    assert evaluate_layer_quality(low)["quality_flag"] == QualityFlag.LOW_CONFIDENCE


def test_stats_empty_are_none_not_zero():
    s = calc_stats(np.full((3, 3), np.nan, np.float32))
    assert s["count"] == 0 and s["mean"] is None and s["max"] is None
    s2 = calc_stats(np.array([[1.0, 3.0], [np.nan, 100.0]], np.float32), np.array([[True, True], [True, False]]))
    assert s2["count"] == 2 and s2["mean"] == 2.0


def test_cross_check_window_and_values():
    s2 = np.array([0.5, 0.6, 0.7, np.nan], dtype=np.float32)
    ls = np.array([0.52, 0.58, 0.69, 0.4], dtype=np.float32)
    res = cross_check_ndvi(s2, ls, time_diff_days=1.5)
    assert res["available"] and res["pixel_count"] == 3
    assert np.isclose(res["mean_diff"], np.mean([-0.02, 0.02, 0.01]), atol=1e-4)
    assert cross_check_ndvi(s2, ls, time_diff_days=3.5)["available"] is False
    assert cross_check_ndvi(np.full(3, np.nan, np.float32), ls[:3], 1.0)["available"] is False


def test_delta_and_transitions():
    d = compute_delta_array(np.array([0.5, np.nan], np.float32), np.array([0.3, 0.1], np.float32))
    assert np.isclose(d[0], 0.2) and np.isnan(d[1])
    curr = np.array([1, 4, 3, 0], dtype=np.uint8)
    prev = np.array([1, 6, 3, 4], dtype=np.uint8)
    res = compute_class_transitions(curr, prev)
    assert res["compared_pixels"] == 3  # noma'lum (0) chiqarib tashlanadi
    assert res["transitions"][0]["from_code"] == 6 and res["transitions"][0]["to_code"] == 4
    assert np.isclose(res["changed_pct"], 100 / 3, atol=0.01)
    m = class_change_mask(curr, prev)
    assert list(m[:3]) == [0.0, 1.0, 0.0] and np.isnan(m[3])
