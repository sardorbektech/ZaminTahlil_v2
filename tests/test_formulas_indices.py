"""Spektral indekslar va RGB formulalari: qiymatlar, nolga bo'lish va NaN."""

import numpy as np
import pytest

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
from backend.app.analysis.formulas.rgb import (
    compute_brightness,
    compute_chromaticity_green,
    compute_excess_green,
    compute_texture_std,
)

A = np.array


def f32(*v: float) -> np.ndarray:
    return A(v, dtype=np.float32)


@pytest.mark.parametrize(
    ("fn", "a", "b", "expected"),
    [
        (compute_ndvi, 0.8, 0.2, 0.6),  # (NIR-Red)/(NIR+Red)
        (compute_ndre, 0.5, 0.3, 0.25),  # (B8A-B5)/(B8A+B5)
        (compute_ndwi, 0.2, 0.6, -0.5),  # (Green-NIR)/(Green+NIR)
        (compute_mndwi, 0.3, 0.1, 0.5),  # (Green-SWIR1)/(Green+SWIR1)
        (compute_ndmi, 0.6, 0.2, 0.5),  # (NIR-SWIR1)/(NIR+SWIR1)
        (compute_nbr, 0.6, 0.4, 0.2),  # (NIR-SWIR2)/(NIR+SWIR2)
        (compute_ndbi, 0.3, 0.1, 0.5),  # (SWIR1-NIR)/(SWIR1+NIR)
    ],
)
def test_normalized_difference_values_zero_div_and_nan(fn, a, b, expected):
    out = fn(f32(a, 0.0, np.nan), f32(b, 0.0, 0.1))
    assert out.dtype == np.float32
    assert np.isclose(out[0], expected)
    assert np.isnan(out[1])  # 0/0 → NaN
    assert np.isnan(out[2])  # NaN kirish → NaN


def test_evi_formula_and_zero_division():
    nir, red, blue = f32(0.5, 0.0), f32(0.1, 0.0), f32(0.05, 1.0 / 7.5)
    out = compute_evi(nir, red, blue)
    assert np.isclose(out[0], 2.5 * 0.4 / (0.5 + 0.6 - 0.375 + 1.0))
    assert np.isnan(out[1])  # mahraj: 0 + 0 − 1 + 1 = 0


def test_bsi_formula_and_zero_division():
    out = compute_bsi(f32(0.3, 0.0), f32(0.2, 0.0), f32(0.25, 0.0), f32(0.05, 0.0))
    assert np.isclose(out[0], ((0.3 + 0.2) - (0.25 + 0.05)) / ((0.3 + 0.2) + (0.25 + 0.05)))
    assert np.isnan(out[1])


def test_rgb_features():
    r, g, b = f32(0.1, 0.0), f32(0.3, 0.0), f32(0.1, 0.0)
    assert np.isclose(compute_brightness(r, g, b)[0], 0.5 / 3)
    assert np.isclose(compute_chromaticity_green(r, g, b)[0], 0.6)
    assert np.isnan(compute_chromaticity_green(r, g, b)[1])
    assert np.isclose(compute_excess_green(r, g, b)[0], (0.6 - 0.1 - 0.1) / 0.5)
    assert np.isnan(compute_excess_green(r, g, b)[1])


def test_texture_ignores_nan_and_flat_is_zero():
    img = np.full((7, 7), 0.2, dtype=np.float32)
    img[0, 0] = np.nan
    tex = compute_texture_std(img)
    assert np.isnan(tex[0, 0])
    assert np.allclose(tex[3, 3], 0.0)
    img[3, 3] = 0.8
    assert compute_texture_std(img)[3, 3] > 0.05
    assert np.all(np.isnan(compute_texture_std(np.full((3, 3), np.nan, np.float32))))
