"""Relyef: Horn nishablik/aspekt, hillshade, TRI, TPI, pastqamliklar."""

import numpy as np

from backend.app.analysis.formulas.terrain import (
    compute_depressions,
    compute_hillshade,
    compute_slope_and_aspect_horn,
    compute_tpi,
    compute_tri,
)


def _plane(dx: float, dy: float, n: int = 7) -> np.ndarray:
    y, x = np.mgrid[0:n, 0:n]
    return (x * dx + y * dy).astype(np.float32)


def test_slope_known_value_and_edges_nan():
    dem = _plane(10.0, 0.0)  # har 10 m da 10 m ko'tarilish → 45°
    slope, aspect = compute_slope_and_aspect_horn(dem, cell_size_m=10.0)
    assert np.allclose(slope[1:-1, 1:-1], 45.0)
    assert np.isnan(slope[0, 0]) and np.isnan(slope[-1, 3])
    # Sharqqa ko'tariladi → yon bag'ir g'arbga qaragan (270°)
    assert np.allclose(aspect[1:-1, 1:-1], 270.0)


def test_aspect_north_facing_and_flat_nan():
    # Qatorlar janubga qarab (pastga) balandlik ortadi → yon bag'ir shimolga qaragan (0°)
    _, aspect = compute_slope_and_aspect_horn(_plane(0.0, 5.0), cell_size_m=10.0)
    assert np.allclose(aspect[1:-1, 1:-1] % 360.0, 0.0)
    slope, aspect = compute_slope_and_aspect_horn(np.full((5, 5), 100.0, np.float32), 10.0)
    assert np.allclose(slope[1:-1, 1:-1], 0.0)
    assert np.all(np.isnan(aspect[1:-1, 1:-1]))


def test_hillshade_flat_and_range():
    slope = np.zeros((3, 3), np.float32)
    aspect = np.full((3, 3), np.nan, np.float32)
    hs = compute_hillshade(slope, aspect, altitude_deg=45.0)
    assert np.allclose(hs, 255.0 * np.cos(np.radians(45.0)))
    slope2, aspect2 = compute_slope_and_aspect_horn(_plane(10.0, 3.0), 10.0)
    hs2 = compute_hillshade(slope2, aspect2)
    assert np.all((hs2[1:-1, 1:-1] >= 0) & (hs2[1:-1, 1:-1] <= 255))
    assert np.isnan(hs2[0, 0])


def test_tri_tpi_and_depressions():
    dem = np.full((7, 7), 100.0, np.float32)
    dem[3, 3] = 95.0  # chuqurlik
    tri = compute_tri(dem)
    assert np.isclose(tri[3, 3], np.sqrt(8 * 25.0))
    tpi = compute_tpi(dem)
    assert tpi[3, 3] < -1.0
    slope, _ = compute_slope_and_aspect_horn(np.full((7, 7), 100.0, np.float32), 10.0)
    dep = compute_depressions(tpi, slope)
    assert dep[3, 3] == 1.0
    assert np.isnan(dep[0, 0])  # chegarada slope yo'q → NaN, 0 emas
    nan_dem = dem.copy()
    nan_dem[1, 1] = np.nan
    assert np.isnan(compute_tpi(nan_dem)[1, 1])
