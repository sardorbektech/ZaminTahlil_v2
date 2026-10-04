"""Relyef morfometriyasi testlari (Horn slope/aspect, hillshade, TRI, TPI)."""

import numpy as np

from backend.app.analysis.formulas.terrain import (
    compute_depressions,
    compute_hillshade,
    compute_slope_and_aspect_horn,
    compute_tpi,
    compute_tri,
)


def test_terrain_derivatives():
    # Nishabli tekislik: x yo'nalishida balandlik ortib boradi
    dem = np.zeros((10, 10), dtype=np.float32)
    for x in range(10):
        dem[:, x] = x * 10.0  # har 30 metrda 10 metr balandlik

    slope, aspect = compute_slope_and_aspect_horn(dem, cell_size_m=30.0)
    assert slope.shape == (10, 10)
    assert aspect.shape == (10, 10)

    # O'rtadagi piksellar nishabligi musbat bo'lishi kerak
    valid_slope = slope[1:-1, 1:-1]
    assert np.all(valid_slope > 0.0)

    hillshade = compute_hillshade(slope, aspect)
    valid_hs = hillshade[1:-1, 1:-1]
    assert np.all((valid_hs >= 0.0) & (valid_hs <= 255.0))

    tri = compute_tri(dem)
    assert tri.shape == (10, 10)

    tpi = compute_tpi(dem)
    assert tpi.shape == (10, 10)

    depressions = compute_depressions(tpi, slope)
    assert depressions.shape == (10, 10)
