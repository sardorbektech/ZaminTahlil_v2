"""Spektral indekslar formulalari testlari (nolga bo'lish, NaN va chegaraviy holatlar)."""

import numpy as np

from backend.app.analysis.formulas.indices import (
    compute_bsi,
    compute_evi,
    compute_mndwi,
    compute_nbr,
    compute_ndbi,
    compute_ndmi,
    compute_ndre,
    compute_ndvi,
    compute_ndwi,
)


def test_ndvi_normal_and_zero_division():
    nir = np.array([0.8, 0.0, 0.4], dtype=np.float32)
    red = np.array([0.2, 0.0, 0.4], dtype=np.float32)

    ndvi = compute_ndvi(nir, red)
    # (0.8 - 0.2) / (0.8 + 0.2) = 0.6
    assert np.isclose(ndvi[0], 0.6)
    # Nolga bo'lish (0.0 - 0.0) / (0.0 + 0.0) -> NaN
    assert np.isnan(ndvi[1])
    # (0.4 - 0.4) / (0.4 + 0.4) = 0.0
    assert np.isclose(ndvi[2], 0.0)


def test_all_indices_produce_valid_arrays():
    b2 = np.full((5, 5), 0.1, dtype=np.float32)
    b3 = np.full((5, 5), 0.15, dtype=np.float32)
    b4 = np.full((5, 5), 0.12, dtype=np.float32)
    b5 = np.full((5, 5), 0.14, dtype=np.float32)
    b8 = np.full((5, 5), 0.45, dtype=np.float32)
    b8a = np.full((5, 5), 0.42, dtype=np.float32)
    b11 = np.full((5, 5), 0.22, dtype=np.float32)
    b12 = np.full((5, 5), 0.18, dtype=np.float32)

    ndvi = compute_ndvi(b8, b4)
    evi = compute_evi(b8, b4, b2)
    ndre = compute_ndre(b8a, b5)
    ndwi = compute_ndwi(b3, b8)
    mndwi = compute_mndwi(b3, b11)
    ndmi = compute_ndmi(b8, b11)
    nbr = compute_nbr(b8, b12)
    ndbi = compute_ndbi(b11, b8)
    bsi = compute_bsi(b11, b4, b8, b2)

    for arr in [ndvi, evi, ndre, ndwi, mndwi, ndmi, nbr, ndbi, bsi]:
        assert arr.shape == (5, 5)
        assert not np.any(np.isnan(arr))
