"""Yer qoplami klassifikatsiyasi va ishonchlilik baholash testlari."""

import numpy as np

from backend.app.analysis.landcover import classify_landcover
from backend.app.core.constants import CLASS_FOREST, CLASS_WATER


def test_classify_water_and_forest():
    # 5x5 massivlar
    ndvi = np.full((5, 5), 0.1, dtype=np.float32)
    ndwi = np.full((5, 5), -0.2, dtype=np.float32)
    mndwi = np.full((5, 5), -0.2, dtype=np.float32)
    ndmi = np.full((5, 5), 0.0, dtype=np.float32)
    bsi = np.full((5, 5), 0.1, dtype=np.float32)
    ndbi = np.full((5, 5), -0.1, dtype=np.float32)
    nbr = np.full((5, 5), 0.2, dtype=np.float32)

    # 1-piksel: Suv (yuqori NDWI va MNDWI)
    ndwi[0, 0] = 0.4
    mndwi[0, 0] = 0.5
    ndvi[0, 0] = -0.3

    # 2-piksel: O'rmon / Daraxtzor (yuqori NDVI)
    ndvi[1, 1] = 0.75
    ndwi[1, 1] = -0.4

    classes, conf = classify_landcover(
        ndvi=ndvi,
        ndwi=ndwi,
        mndwi=mndwi,
        ndmi=ndmi,
        bsi=bsi,
        ndbi=ndbi,
        nbr=nbr,
    )

    assert classes[0, 0] == CLASS_WATER
    assert conf[0, 0] >= 0.8

    assert classes[1, 1] == CLASS_FOREST
    assert conf[1, 1] >= 0.8
