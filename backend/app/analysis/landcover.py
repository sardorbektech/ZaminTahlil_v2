"""Yer qoplamini qoidalar asosida 10 ta sinfga klassifikatsiya qilish moduli.

Mantiqiy qoidalar, ostonaviy qiymatlar va ishonchlilik (confidence score) baholash.
"""

import numpy as np
from scipy.ndimage import binary_dilation, label

from backend.app.core.constants import (
    CLASS_BARE_SOIL,
    CLASS_BRIDGE,
    CLASS_BUILTUP,
    CLASS_BURNT,
    CLASS_CROPLAND,
    CLASS_FOREST,
    CLASS_ROAD,
    CLASS_SPARSE_VEG,
    CLASS_SWAMP,
    CLASS_UNKNOWN,
    CLASS_WATER,
)


def classify_landcover(
    ndvi: np.ndarray,
    ndwi: np.ndarray,
    mndwi: np.ndarray,
    ndmi: np.ndarray,
    bsi: np.ndarray,
    ndbi: np.ndarray,
    nbr: np.ndarray,
    vv_db: np.ndarray | None = None,
    vh_db: np.ndarray | None = None,
    texture: np.ndarray | None = None,
    depression_mask: np.ndarray | None = None,
    soil_moisture: np.ndarray | None = None,
    cloud_mask: np.ndarray | None = None,
    s2_scl: np.ndarray | None = None,
    delta_nbr: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Yer qoplamini 10 ta sinfga ajratadi va har bir piksel ishonchliligini hisoblaydi.

    Qaytaradi:
        (classes, confidence):
            classes - uint8 turdagi 0 dan 10 gacha bo'lgan sinf kodlari
            confidence - float32 turdagi 0.0 dan 1.0 gacha bo'lgan ishonchlilik darajasi
    """
    rows, cols = ndvi.shape
    classes = np.full((rows, cols), CLASS_UNKNOWN, dtype=np.uint8)
    confidence = np.full((rows, cols), 0.5, dtype=np.float32)

    # 1. Bulut va yaroqsiz piksellar
    is_invalid = np.isnan(ndvi) | np.isnan(ndwi)
    if cloud_mask is not None:
        is_invalid |= cloud_mask.astype(bool)

    # Dastlabki asosiy shartlar
    # Suv: MNDWI > 0.1 yoki NDWI > 0.2
    is_water_opt = (mndwi > 0.1) | (ndwi > 0.2)
    if vv_db is not None:
        is_water = is_water_opt | (vv_db < -15.0)
    else:
        is_water = is_water_opt

    # Kuygan hudud: past NBR va NBR pasayishi
    if delta_nbr is not None:
        is_burnt = (nbr < 0.1) & (delta_nbr < -0.2)
    else:
        is_burnt = nbr < -0.15

    # Botqoqlik: o'rtacha NDWI/NDMI, NDVI 0.1-0.5, pastqamlik
    is_swamp = (ndwi > 0.0) & (ndvi >= 0.1) & (ndvi <= 0.5)
    if depression_mask is not None:
        is_swamp &= depression_mask > 0.5
    if soil_moisture is not None:
        is_swamp &= soil_moisture > 0.35

    # Daraxtzor: NDVI > 0.6
    is_forest = ndvi > 0.6
    if texture is not None:
        is_forest &= texture > 0.04

    # Ekin / dala: NDVI 0.3 - 0.6
    is_crop = (ndvi >= 0.3) & (ndvi <= 0.6)
    if texture is not None:
        is_crop &= texture <= 0.06

    # Siyrak o'simlik: NDVI 0.15 - 0.3
    is_sparse = (ndvi >= 0.15) & (ndvi < 0.3)

    # Ochiq tuproq: BSI > 0, NDVI < 0.15
    is_bare = (bsi > 0.0) & (ndvi < 0.15)

    # Imorat: NDBI > 0, past NDVI
    is_builtup = (ndbi > 0.0) & (ndvi < 0.25)
    if vv_db is not None:
        is_builtup &= vv_db > -10.0

    # Sinflarni ketma-ket joylashtirish (prioritetlar bilan)
    # Avval fon: ochiq tuproq
    classes[is_bare] = CLASS_BARE_SOIL
    confidence[is_bare] = 0.80

    classes[is_sparse] = CLASS_SPARSE_VEG
    confidence[is_sparse] = 0.80

    classes[is_crop] = CLASS_CROPLAND
    confidence[is_crop] = 0.85

    classes[is_forest] = CLASS_FOREST
    confidence[is_forest] = 0.90

    classes[is_builtup] = CLASS_BUILTUP
    confidence[is_builtup] = 0.85

    classes[is_swamp] = CLASS_SWAMP
    confidence[is_swamp] = 0.75

    classes[is_burnt] = CLASS_BURNT
    confidence[is_burnt] = 0.80

    classes[is_water] = CLASS_WATER
    confidence[is_water] = 0.95

    # 8. Yo'llar (ehtimoliy): imorat yoki ochiq tuproq piksellarining cho'zilgan komponentlari
    road_candidates = (classes == CLASS_BUILTUP) | (classes == CLASS_BARE_SOIL)
    labeled_comp, num_comp = label(road_candidates)
    if num_comp > 0:
        for c_id in range(1, min(num_comp + 1, 500)):
            comp_mask = labeled_comp == c_id
            count = np.sum(comp_mask)
            if 15 <= count <= 3000:
                y_idx, x_idx = np.where(comp_mask)
                dx = np.max(x_idx) - np.min(x_idx) + 1
                dy = np.max(y_idx) - np.min(y_idx) + 1
                aspect_ratio = max(dx, dy) / (min(dx, dy) + 1e-5)
                if aspect_ratio > 3.5:
                    classes[comp_mask] = CLASS_ROAD
                    confidence[comp_mask] = 0.70

    # 9. Ko'priklar (ehtimoliy): yo'l yoki imorat piksellari suv bilan kesishganda
    is_water_pixels = classes == CLASS_WATER
    water_dilated = binary_dilation(is_water_pixels, iterations=2)
    bridge_mask = (classes == CLASS_ROAD) & water_dilated
    classes[bridge_mask] = CLASS_BRIDGE
    confidence[bridge_mask] = 0.65

    # Noma'lum / bulut
    classes[is_invalid] = CLASS_UNKNOWN
    confidence[is_invalid] = 0.0

    # S2 SCL bilan taqqoslab ishonchlilikni pasaytirish
    if s2_scl is not None:
        # SCL: 3 - Cloud Shadow, 4 - Vegetation, 5 - Not-vegetated, 6 - Water, 8,9,10 - Clouds, 11 - Snow
        scl_disagree = np.zeros((rows, cols), dtype=bool)
        scl_disagree |= (classes == CLASS_WATER) & (s2_scl != 6)
        scl_disagree |= (classes == CLASS_FOREST) & (s2_scl != 4)
        scl_disagree |= (classes == CLASS_BARE_SOIL) & (~np.isin(s2_scl, [4, 5]))
        confidence[scl_disagree] = np.maximum(confidence[scl_disagree] - 0.25, 0.1)

    return classes, confidence
