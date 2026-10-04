"""Yer qoplamini qoidalar asosida sinflarga ajratish (SIMPLE.md §7.4).

Barcha chegaralar core/constants.py da. Kirish massivlari float32, NaN — ma'lumot yo'q.
NaN bilan taqqoslash har doim False beradi, shuning uchun yo'q dalil hech qachon "bor" deb hisoblanmaydi.
"""

import numpy as np
from scipy.ndimage import binary_dilation, find_objects, label

from backend.app.core import constants as C


def _gt(a: np.ndarray | None, v: float) -> np.ndarray | None:
    if a is None:
        return None
    with np.errstate(invalid="ignore"):
        return a > v


def _lt(a: np.ndarray | None, v: float) -> np.ndarray | None:
    if a is None:
        return None
    with np.errstate(invalid="ignore"):
        return a < v


def _between(a: np.ndarray, lo: float, hi: float) -> np.ndarray:
    with np.errstate(invalid="ignore"):
        return (a >= lo) & (a <= hi)


def find_road_components(candidates: np.ndarray) -> np.ndarray:
    """Cho'zilgan bog'langan komponentlarni (ehtimoliy yo'llar) topadi.

    Har bir 8-bog'langan komponent uchun piksel koordinatalari kovariatsiyasining xos qiymatlari
    λ1 ≥ λ2 olinadi: cho'zilganlik = √(λ1/λ2). Shuningdek to'ldirish nisbati =
    piksellar / (chegaralovchi to'rtburchak maydoni) — diagonal yo'llarni ham ushlash uchun
    burilgan to'rtburchak o'rniga o'q bo'yicha uzunlik × o'rtacha kenglik ishlatiladi.
    Shart: piksellar ≥ LC_ROAD_MIN_PIXELS va cho'zilganlik ≥ LC_ROAD_MIN_ELONGATION.
    """
    out = np.zeros(candidates.shape, dtype=bool)
    structure = np.ones((3, 3), dtype=bool)
    labeled, n = label(candidates, structure=structure)
    if n == 0:
        return out
    for idx, sl in enumerate(find_objects(labeled), start=1):
        if sl is None:
            continue
        comp = labeled[sl] == idx
        count = int(comp.sum())
        if count < C.LC_ROAD_MIN_PIXELS:
            continue
        ys, xs = np.nonzero(comp)
        if count < 3:
            continue
        cov = np.cov(np.vstack([xs, ys]).astype(np.float64))
        ev = np.sort(np.linalg.eigvalsh(cov))[::-1]
        major = max(ev[0], 1e-9)
        minor = max(ev[1], 1.0 / 12.0)  # bir piksel kenglikdagi chiziq dispersiyasi
        elong = float(np.sqrt(major / minor))
        if elong < C.LC_ROAD_MIN_ELONGATION:
            continue
        # Yo'l ingichka bo'ladi: uzunlik (≈ √(12·λ1)) bo'yicha o'rtacha kenglik kichik
        length = float(np.sqrt(12.0 * major))
        mean_width = count / max(length, 1.0)
        if mean_width / max(length, 1.0) > C.LC_ROAD_MAX_FILL_RATIO:
            continue
        out[sl] |= comp
    return out


def find_bridge_pixels(structure_mask: np.ndarray, water: np.ndarray, reach_px: int = 3) -> np.ndarray:
    """Suvni kesib o'tuvchi yo'l/imorat piksellari (ehtimoliy ko'prik).

    Piksel ko'prik hisoblanadi, agar u suvga tegib turgan bo'lsa va uning ikki qarama-qarshi
    tomonida (chap/o'ng yoki yuqori/past) reach_px masofa ichida suv bo'lsa.
    """
    near = binary_dilation(water, iterations=C.LC_BRIDGE_WATER_DILATION_PX)
    h, w = water.shape

    def shifted_any(dy: int, dx: int) -> np.ndarray:
        acc = np.zeros_like(water)
        for k in range(1, reach_px + 1):
            src = np.zeros_like(water)
            ys = slice(max(0, -dy * k), h - max(0, dy * k))
            yd = slice(max(0, dy * k), h - max(0, -dy * k))
            xs = slice(max(0, -dx * k), w - max(0, dx * k))
            xd = slice(max(0, dx * k), w - max(0, -dx * k))
            src[yd, xd] = water[ys, xs]
            acc |= src
        return acc

    left, right = shifted_any(0, 1), shifted_any(0, -1)
    up, down = shifted_any(1, 0), shifted_any(-1, 0)
    crossing = (left & right) | (up & down)
    return structure_mask & near & crossing


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
    """Yer qoplamini 0–10 sinflarga ajratadi va har bir piksel uchun ishonchlilikni (0–1) beradi.

    Qoidalar (ustuvorlik tartibida, keyingisi oldingisini ustidan yozadi):
        6 Ochiq tuproq: BSI > 0 va NDVI < 0.15
        5 Siyrak o'simlik: 0.15 ≤ NDVI < 0.3
        4 Ekin/dala: 0.3 ≤ NDVI ≤ 0.6 (tekstura past; yuqori bo'lsa ishonch pasayadi)
        3 Daraxtzor: NDVI > 0.6 va (tekstura yuqori yoki VH yuqori); aks holda ekin
        2 Botqoqlik: 0.1 ≤ NDVI ≤ 0.5 va 5 ta dalildan ≥ 3 tasi
           (NDWI o'rtacha, NDMI o'rtacha, pastqamlik, past VV, yuqori tuproq namligi)
        7 Imorat: NDBI > 0, NDVI < 0.2 va (VV yuqori; SAR yo'q bo'lsa — tekstura yuqori)
        10 Kuygan hudud: NBR < 0.1 va ΔNBR < −0.27 (oldingi kuzatuv bo'lsagina)
        1 Suv: MNDWI > 0.1 yoki NDWI > 0.2 (SAR past qaytishi tasdiqlasa ishonch yuqori)
        8 Yo'l: imorat/ochiq tuproqning cho'zilgan bog'langan komponentlari
        9 Ko'prik: suvni kesib o'tgan yo'l/imorat piksellari
        0 Noma'lum/bulut: niqoblangan yoki indeks hisoblanmagan piksellar
    Ishonchlilik S2 SCL bilan ziddiyatda LC_CONF_SCL_PENALTY ga pasaytiriladi.
    """
    shape = ndvi.shape
    classes = np.full(shape, C.CLASS_UNKNOWN, dtype=np.uint8)
    conf = np.zeros(shape, dtype=np.float32)

    invalid = np.isnan(ndvi) | np.isnan(ndwi) | np.isnan(mndwi) | np.isnan(bsi) | np.isnan(ndbi)
    if cloud_mask is not None:
        invalid |= cloud_mask.astype(bool)

    def assign(mask: np.ndarray, code: int, conf_scale: np.ndarray | float = 1.0) -> None:
        m = mask & ~invalid
        classes[m] = code
        base = C.LC_CONF_BASE[code]
        conf[m] = (base * conf_scale)[m] if isinstance(conf_scale, np.ndarray) else base * conf_scale

    high_texture = _gt(texture, C.LC_FOREST_TEXTURE_MIN)
    low_texture = _lt(texture, C.LC_CROP_TEXTURE_MAX)

    # 6. Ochiq tuproq
    with np.errstate(invalid="ignore"):
        bare = (bsi > C.LC_BARE_BSI_MIN) & (ndvi < C.LC_BARE_NDVI_MAX)
    assign(bare, C.CLASS_BARE_SOIL)

    # 5. Siyrak o'simlik
    with np.errstate(invalid="ignore"):
        sparse = (ndvi >= C.LC_SPARSE_NDVI_RANGE[0]) & (ndvi < C.LC_SPARSE_NDVI_RANGE[1])
    assign(sparse, C.CLASS_SPARSE_VEG)

    # 4. Ekin / dala
    crop = _between(ndvi, *C.LC_CROP_NDVI_RANGE)
    crop_scale = np.ones(shape, dtype=np.float32)
    if low_texture is not None:
        crop_scale[~low_texture] = 0.8
    assign(crop, C.CLASS_CROPLAND, crop_scale)

    # 3. Daraxtzor
    with np.errstate(invalid="ignore"):
        dense = ndvi > C.LC_FOREST_NDVI_MIN
    tree_evidence = np.zeros(shape, dtype=bool)
    if high_texture is not None:
        tree_evidence |= high_texture
    vh_high = _gt(vh_db, C.LC_FOREST_VH_MIN_DB)
    if vh_high is not None:
        tree_evidence |= vh_high
    assign(dense & tree_evidence, C.CLASS_FOREST)
    assign(dense & ~tree_evidence, C.CLASS_CROPLAND, 0.8)  # zich, lekin bir xil — zich ekin

    # 2. Botqoqlik (dalillar soni)
    swamp_ndvi = _between(ndvi, *C.LC_SWAMP_NDVI_RANGE)
    evidence = np.zeros(shape, dtype=np.int8)
    available = np.zeros(shape, dtype=np.int8)
    for ev in (
        _gt(ndwi, C.LC_SWAMP_NDWI_MIN),
        _gt(ndmi, C.LC_SWAMP_NDMI_MIN),
        _gt(depression_mask, 0.5),
        _lt(vv_db, C.LC_SWAMP_VV_MAX_DB),
        _gt(soil_moisture, C.LC_SWAMP_SM_MIN),
    ):
        if ev is not None:
            evidence += ev.astype(np.int8)
            available += 1
    if int(available.max(initial=0)) >= C.LC_SWAMP_MIN_EVIDENCE:
        swamp = swamp_ndvi & (evidence >= C.LC_SWAMP_MIN_EVIDENCE)
        swamp_scale = np.clip(evidence / np.maximum(available, 1), 0.0, 1.0).astype(np.float32) + 0.4
        assign(swamp, C.CLASS_SWAMP, np.minimum(swamp_scale, 1.0))

    # 7. Imorat
    with np.errstate(invalid="ignore"):
        built_opt = (ndbi > C.LC_BUILT_NDBI_MIN) & (ndvi < C.LC_BUILT_NDVI_MAX)
    vv_high = _gt(vv_db, C.LC_BUILT_VV_MIN_DB)
    if vv_high is not None:
        sar_ok = ~np.isnan(vv_db)
        built = built_opt & ((sar_ok & vv_high) | (~sar_ok & (high_texture if high_texture is not None else False)))
    else:
        built = built_opt & (high_texture if high_texture is not None else np.zeros(shape, dtype=bool))
    assign(built, C.CLASS_BUILTUP, 1.0 if vv_db is not None else 0.8)

    # 10. Kuygan hudud (faqat NBR pasayishi ma'lum bo'lsa)
    if delta_nbr is not None:
        with np.errstate(invalid="ignore"):
            burnt = (nbr < C.LC_BURNT_NBR_MAX) & (delta_nbr < C.LC_BURNT_DNBR_MAX)
        assign(burnt, C.CLASS_BURNT)

    # 1. Suv
    with np.errstate(invalid="ignore"):
        water_opt = (mndwi > C.LC_WATER_MNDWI_MIN) | (ndwi > C.LC_WATER_NDWI_MIN)
    water_scale = np.ones(shape, dtype=np.float32)
    if vv_db is not None:
        low_bs = _lt(vv_db, C.LC_WATER_VV_MAX_DB)
        if vh_db is not None:
            low_bs = low_bs | _lt(vh_db, C.LC_WATER_VH_MAX_DB)
        sar_known = ~np.isnan(vv_db)
        water_scale[sar_known & ~low_bs] = 0.7  # SAR suvni tasdiqlamadi
    assign(water_opt, C.CLASS_WATER, water_scale)

    # 8. Yo'l (ehtimoliy)
    roads = find_road_components((classes == C.CLASS_BUILTUP) | (classes == C.CLASS_BARE_SOIL))
    assign(roads, C.CLASS_ROAD)

    # 9. Ko'prik (ehtimoliy)
    water = classes == C.CLASS_WATER
    if water.any():
        bridges = find_bridge_pixels((classes == C.CLASS_ROAD) | (classes == C.CLASS_BUILTUP), water)
        assign(bridges, C.CLASS_BRIDGE)

    # 0. Noma'lum / bulut
    classes[invalid] = C.CLASS_UNKNOWN
    conf[invalid] = 0.0

    # S2 SCL bilan muvofiqlik
    if s2_scl is not None:
        scl = np.nan_to_num(s2_scl, nan=0).astype(np.int16)
        scl_known = ~np.isnan(s2_scl)
        disagree = np.zeros(shape, dtype=bool)
        disagree |= (classes == C.CLASS_WATER) & (scl != C.SCL_WATER)
        disagree |= np.isin(classes, (C.CLASS_FOREST, C.CLASS_CROPLAND, C.CLASS_SPARSE_VEG)) & (
            scl != C.SCL_VEGETATION
        )
        disagree |= np.isin(classes, (C.CLASS_BARE_SOIL, C.CLASS_BUILTUP, C.CLASS_ROAD)) & (
            scl != C.SCL_NOT_VEGETATED
        )
        disagree &= scl_known & (classes != C.CLASS_UNKNOWN)
        conf[disagree] = np.maximum(conf[disagree] - C.LC_CONF_SCL_PENALTY, C.LC_CONF_MIN)

    return classes, conf
