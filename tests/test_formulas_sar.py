"""SAR tahlili testlari (Lee 5x5 filter, dB, RVI, suv niqobi)."""

import numpy as np

from backend.app.analysis.formulas.sar import (
    compute_rvi,
    compute_sar_water_mask,
    db_to_linear,
    lee_filter_5x5,
    linear_to_db,
)


def test_db_conversions():
    db = np.array([-10.0, 0.0, 10.0], dtype=np.float32)
    lin = db_to_linear(db)
    assert np.isclose(lin[0], 0.1)
    assert np.isclose(lin[1], 1.0)
    assert np.isclose(lin[2], 10.0)

    back_to_db = linear_to_db(lin)
    assert np.allclose(db, back_to_db)


def test_lee_filter_smoothing():
    np.random.seed(42)
    # Shovqinli massiv
    base = np.full((15, 15), 10.0, dtype=np.float32)
    noise = np.random.normal(0, 2.0, (15, 15)).astype(np.float32)
    img = base + noise

    filtered = lee_filter_5x5(img)
    assert filtered.shape == (15, 15)
    # Filtrlangan massiv dispersiyasi asl massivnikidan kichikroq bo'lishi kerak
    assert np.var(filtered) < np.var(img)


def test_sar_water_mask():
    vv = np.array([-20.0, -16.0, -14.0, -10.0], dtype=np.float32)
    # -15 dB dan past bo'lganlar suv (1.0)
    mask = compute_sar_water_mask(vv, threshold_db=-15.0)
    assert mask[0] == 1.0
    assert mask[1] == 1.0
    assert mask[2] == 0.0
    assert mask[3] == 0.0


def test_rvi_calculation():
    vv = np.array([-12.0], dtype=np.float32)
    vh = np.array([-18.0], dtype=np.float32)
    rvi = compute_rvi(vh, vv)
    assert 0.0 <= rvi[0] <= 1.0
