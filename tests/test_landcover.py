"""Yer qoplami qoidalari (§7.4): har bir sinf, NaN/bulut, SCL bo'yicha ishonchlilik."""

import numpy as np

from backend.app.analysis.landcover import (
    classify_landcover,
    find_bridge_pixels,
    find_road_components,
)
from backend.app.core import constants as C

N = 12


def base(**over: float) -> dict[str, np.ndarray]:
    """Fon: siyrak o'simlik."""
    vals = {"ndvi": 0.2, "ndwi": -0.3, "mndwi": -0.2, "ndmi": -0.1, "bsi": -0.05, "ndbi": -0.1, "nbr": 0.3}
    vals.update(over)
    return {k: np.full((N, N), v, np.float32) for k, v in vals.items()}


def classify(arrs: dict[str, np.ndarray], **kw):
    return classify_landcover(**arrs, **kw)


def test_basic_vegetation_classes():
    for ndvi, code in ((0.2, C.CLASS_SPARSE_VEG), (0.45, C.CLASS_CROPLAND)):
        cls, conf = classify(base(ndvi=ndvi), texture=np.zeros((N, N), np.float32))
        assert np.all(cls == code)
        assert np.all(conf > 0)


def test_forest_needs_texture_or_vh():
    tex = np.full((N, N), 0.05, np.float32)
    cls, _ = classify(base(ndvi=0.75), texture=tex)
    assert np.all(cls == C.CLASS_FOREST)
    cls2, _ = classify(base(ndvi=0.75), texture=np.zeros((N, N), np.float32))
    assert np.all(cls2 == C.CLASS_CROPLAND)  # zich, lekin bir xil
    cls3, _ = classify(base(ndvi=0.75), texture=np.zeros((N, N), np.float32), vh_db=np.full((N, N), -14.0, np.float32))
    assert np.all(cls3 == C.CLASS_FOREST)


def test_water_optical_and_sar_confidence():
    a = base(ndvi=-0.1, ndwi=0.4, mndwi=0.5)
    cls, conf = classify(a, vv_db=np.full((N, N), -22.0, np.float32))
    assert np.all(cls == C.CLASS_WATER) and np.allclose(conf, C.LC_CONF_BASE[1])
    _, conf2 = classify(a, vv_db=np.full((N, N), -8.0, np.float32), vh_db=np.full((N, N), -14.0, np.float32))
    assert np.all(conf2 < conf)


def test_bare_and_builtup_with_sar():
    cls, _ = classify(base(ndvi=0.05, bsi=0.1))
    assert np.all((cls == C.CLASS_BARE_SOIL) | (cls == C.CLASS_ROAD))
    cls2, _ = classify(base(ndvi=0.05, bsi=0.1, ndbi=0.1), vv_db=np.full((N, N), -5.0, np.float32))
    assert np.all(cls2 == C.CLASS_BUILTUP)


def test_swamp_needs_evidence():
    a = base(ndvi=0.3, ndwi=0.0, ndmi=0.1)
    dep = np.ones((N, N), np.float32)
    cls, _ = classify(a, depression_mask=dep, vv_db=np.full((N, N), -14.0, np.float32), soil_moisture=np.full((N, N), 0.4, np.float32))
    assert np.all(cls == C.CLASS_SWAMP)
    cls2, _ = classify(a)  # faqat 2 ta dalil → botqoq emas
    assert not np.any(cls2 == C.CLASS_SWAMP)


def test_burnt_requires_nbr_drop():
    a = base(ndvi=0.1, nbr=0.0, bsi=-0.1)
    cls, _ = classify(a)
    assert not np.any(cls == C.CLASS_BURNT)
    cls2, _ = classify(a, delta_nbr=np.full((N, N), -0.4, np.float32))
    assert np.all(cls2 == C.CLASS_BURNT)


def test_masked_and_nan_pixels_are_unknown():
    a = base()
    a["ndvi"][0, 0] = np.nan
    cloud = np.zeros((N, N), bool)
    cloud[1, 1] = True
    cls, conf = classify(a, cloud_mask=cloud)
    assert cls[0, 0] == C.CLASS_UNKNOWN and cls[1, 1] == C.CLASS_UNKNOWN
    assert conf[0, 0] == 0.0 and conf[1, 1] == 0.0


def test_scl_disagreement_lowers_confidence():
    a = base(ndvi=0.45)
    scl_ok = np.full((N, N), 4, np.float32)
    scl_bad = np.full((N, N), 6, np.float32)
    _, c_ok = classify(a, s2_scl=scl_ok, texture=np.zeros((N, N), np.float32))
    _, c_bad = classify(a, s2_scl=scl_bad, texture=np.zeros((N, N), np.float32))
    assert np.allclose(c_ok - c_bad, C.LC_CONF_SCL_PENALTY)


def test_road_component_and_bridge():
    m = np.zeros((30, 30), bool)
    m[15, 2:28] = True  # uzun ingichka chiziq
    m[3:7, 3:7] = True  # kvadrat — yo'l emas
    roads = find_road_components(m)
    assert roads[15, 10] and not roads[4, 4]
    water = np.zeros((30, 30), bool)
    water[10:21, 12:18] = True
    water[15, 12:18] = False  # yo'l suv ustidan o'tadi
    bridge = find_bridge_pixels(roads, water)
    assert bridge[15, 14] and not bridge[15, 3]
