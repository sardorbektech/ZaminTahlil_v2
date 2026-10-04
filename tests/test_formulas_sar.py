"""SAR va termal formulalar: dB, Lee filtri, RVI, suv niqobi, LST, Landsat QA."""

import numpy as np

from backend.app.analysis.formulas.sar import (
    compute_rvi,
    compute_sar_water_mask,
    compute_vh_minus_vv,
    db_to_linear,
    lee_filter_5x5,
    lee_filter_db,
    linear_to_db,
)
from backend.app.analysis.formulas.thermal import (
    compute_landsat_lst_celsius,
    landsat_qa_invalid_mask,
)


def test_db_linear_roundtrip_and_nonpositive():
    db = np.array([-10.0, 0.0, 10.0], dtype=np.float32)
    assert np.allclose(db_to_linear(db), [0.1, 1.0, 10.0])
    assert np.allclose(linear_to_db(db_to_linear(db)), db)
    assert np.all(np.isnan(linear_to_db(np.array([0.0, -1.0], dtype=np.float32))))


def test_lee_filter_reduces_speckle_and_keeps_nan():
    rng = np.random.default_rng(42)
    lin = rng.gamma(4.4, 0.05 / 4.4, (20, 20)).astype(np.float32)  # speckle: o'rtacha 0.05
    lin[5, 5] = np.nan
    out = lee_filter_5x5(lin)
    assert np.isnan(out[5, 5])
    assert np.nanvar(out) < np.nanvar(lin)
    assert abs(np.nanmean(out) - np.nanmean(lin)) < 0.01
    assert np.all(np.isnan(lee_filter_5x5(np.full((4, 4), np.nan, np.float32))))


def test_lee_filter_db_operates_in_linear_domain():
    vv = np.full((9, 9), -12.0, dtype=np.float32)
    assert np.allclose(lee_filter_db(vv), -12.0, atol=1e-4)


def test_rvi_formula_not_clipped():
    vv, vh = np.array([-12.0, -10.0], dtype=np.float32), np.array([-18.0, -10.0], dtype=np.float32)
    rvi = compute_rvi(vh, vv)
    lin_vv, lin_vh = 10 ** (-1.2), 10 ** (-1.8)
    assert np.isclose(rvi[0], 4 * lin_vh / (lin_vv + lin_vh), rtol=1e-5)
    assert np.isclose(rvi[1], 2.0)  # VH = VV → 4/2, kesilmaydi
    assert np.isnan(compute_rvi(np.array([np.nan], np.float32), np.array([-10.0], np.float32))[0])


def test_water_mask_threshold_and_nan():
    vv = np.array([-20.0, -15.0, -10.0, np.nan], dtype=np.float32)
    m = compute_sar_water_mask(vv, threshold_db=-15.0)
    assert m[0] == 1.0 and m[1] == 0.0 and m[2] == 0.0
    assert np.isnan(m[3])  # yo'q ma'lumot 0 emas


def test_vh_minus_vv():
    assert compute_vh_minus_vv(np.array([-18.0], np.float32), np.array([-12.0], np.float32))[0] == -6.0


def test_landsat_lst_scaling():
    dn = np.array([(298.15 - 149.0) / 0.00341802, 0.0, np.nan], dtype=np.float32)
    lst = compute_landsat_lst_celsius(dn)
    assert np.isclose(lst[0], 25.0, atol=0.01)
    assert np.isnan(lst[1]) and np.isnan(lst[2])


def test_landsat_qa_mask_bits():
    qa = np.array([21824, 22280, 1, np.nan, 21824 | (1 << 4)], dtype=np.float32)
    m = landsat_qa_invalid_mask(qa)
    assert list(m) == [False, True, True, True, True]
