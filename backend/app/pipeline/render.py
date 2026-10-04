"""Qatlamlar katalogi, rang palitralari, afsona (legend) va PNG render.

NaN piksellar (AOI tashqarisi, bulut, ma'lumot yo'q) to'liq shaffof (alpha = 0) qilinadi.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from backend.app.core.constants import CLASS_COLORS, CLASS_LABELS_UZ, CLASS_UNKNOWN
from backend.app.db.enums import LayerKind, SensorKind

# Palitralar: rang to'xtash nuqtalari (teng oraliqda)
PALETTES: dict[str, list[str]] = {
    "veg": ["#8c510a", "#d8b365", "#f6e8c3", "#c7e9b4", "#41ab5d", "#00441b"],
    "water": ["#a6611a", "#dfc27d", "#f5f5f5", "#80cdc1", "#2166ac", "#053061"],
    "moist": ["#8c510a", "#dfc27d", "#f5f5f5", "#92c5de", "#2166ac"],
    "burn": ["#b2182b", "#ef8a62", "#fddbc7", "#d9f0d3", "#5aae61", "#1b7837"],
    "built": ["#1a9850", "#f7f7f7", "#fdae61", "#d73027", "#67001f"],
    "gray": ["#000000", "#ffffff"],
    "viridis": ["#440154", "#3b528b", "#21918c", "#5ec962", "#fde725"],
    "thermal": ["#313695", "#4575b4", "#abd9e9", "#ffffbf", "#fdae61", "#d73027", "#a50026"],
    "terrain": ["#1a5d1a", "#7fbf3f", "#e6e68a", "#c8a064", "#8c6239", "#ffffff"],
    "slope": ["#ffffcc", "#fed976", "#fd8d3c", "#e31a1c", "#800026"],
    "cyclic": ["#e41a1c", "#ffff33", "#4daf4a", "#377eb8", "#984ea3", "#e41a1c"],
    "diverge": ["#b2182b", "#ef8a62", "#f7f7f7", "#67a9cf", "#2166ac"],
    "diverge_veg": ["#a50026", "#f46d43", "#f7f7f7", "#66bd63", "#006837"],
    "confidence": ["#d73027", "#fee08b", "#1a9850"],
    "mask": ["#00000000", "#00e5ff"],
    "change": ["#00000000", "#ff00ff"],
}


@dataclass(frozen=True)
class LayerSpec:
    """Qatlam tavsifi: tur, nom, birlik, manba, palitra va qiymat oralig'i."""

    kind: LayerKind
    sensor: SensorKind
    label_uz: str
    unit: str
    palette: str
    vmin: float | None = None  # None — ma'lumotdan (2–98 persentil)
    vmax: float | None = None
    mode: str = "gradient"  # gradient | classes | mask | rgb
    group_uz: str = ""


S2, S1, LS, DEM, SMAP, DER = (
    SensorKind.SENTINEL2,
    SensorKind.SENTINEL1,
    SensorKind.LANDSAT,
    SensorKind.DEM,
    SensorKind.SMAP,
    SensorKind.DERIVED,
)

LAYER_SPECS: dict[str, LayerSpec] = {
    "rgb": LayerSpec(LayerKind.RGB, S2, "Tabiiy ranglar (B4/B3/B2)", "", "", 0.0, 0.3, "rgb", "Optik"),
    "false_color": LayerSpec(LayerKind.FALSE_COLOR, S2, "Soxta rang (B8/B4/B3)", "", "", 0.0, 0.5, "rgb", "Optik"),
    "ndvi": LayerSpec(LayerKind.NDVI, S2, "NDVI — oʻsimlik", "", "veg", -0.2, 0.9, group_uz="Indekslar"),
    "evi": LayerSpec(LayerKind.EVI, S2, "EVI — oʻsimlik", "", "veg", -0.2, 0.9, group_uz="Indekslar"),
    "ndre": LayerSpec(LayerKind.NDRE, S2, "NDRE — qizil chekka", "", "veg", -0.2, 0.7, group_uz="Indekslar"),
    "ndwi": LayerSpec(LayerKind.NDWI, S2, "NDWI — suv", "", "water", -0.6, 0.6, group_uz="Indekslar"),
    "mndwi": LayerSpec(LayerKind.MNDWI, S2, "MNDWI — suv", "", "water", -0.6, 0.6, group_uz="Indekslar"),
    "ndmi": LayerSpec(LayerKind.NDMI, S2, "NDMI — namlik", "", "moist", -0.6, 0.6, group_uz="Indekslar"),
    "nbr": LayerSpec(LayerKind.NBR, S2, "NBR — yongʻin", "", "burn", -0.5, 0.9, group_uz="Indekslar"),
    "ndbi": LayerSpec(LayerKind.NDBI, S2, "NDBI — imorat", "", "built", -0.6, 0.4, group_uz="Indekslar"),
    "bsi": LayerSpec(LayerKind.BSI, S2, "BSI — ochiq tuproq", "", "built", -0.6, 0.4, group_uz="Indekslar"),
    "brightness": LayerSpec(LayerKind.BRIGHTNESS, S2, "Yorqinlik", "", "gray", 0.0, 0.35, group_uz="RGB xususiyatlari"),
    "chroma_green": LayerSpec(LayerKind.CHROMA_GREEN, S2, "Yashil xromatiklik", "", "veg", 0.25, 0.45, group_uz="RGB xususiyatlari"),
    "exg": LayerSpec(LayerKind.EXCESS_GREEN, S2, "ExG — yashillik", "", "veg", -0.1, 0.3, group_uz="RGB xususiyatlari"),
    "texture": LayerSpec(LayerKind.TEXTURE, S2, "Tekstura (mahalliy std)", "", "viridis", 0.0, None, group_uz="RGB xususiyatlari"),
    "landcover": LayerSpec(LayerKind.LANDCOVER, DER, "Yer qoplami", "", "", None, None, "classes", "Yer qoplami"),
    "confidence": LayerSpec(LayerKind.CONFIDENCE, DER, "Tasnif ishonchliligi", "", "confidence", 0.0, 1.0, group_uz="Yer qoplami"),
    "vv": LayerSpec(LayerKind.SAR_VV, S1, "SAR VV", "dB", "gray", -25.0, 0.0, group_uz="Radar (SAR)"),
    "vh": LayerSpec(LayerKind.SAR_VH, S1, "SAR VH", "dB", "gray", -30.0, -5.0, group_uz="Radar (SAR)"),
    "vh_minus_vv": LayerSpec(LayerKind.SAR_VH_MINUS_VV, S1, "VH − VV", "dB", "viridis", -15.0, 0.0, group_uz="Radar (SAR)"),
    "rvi": LayerSpec(LayerKind.SAR_RVI, S1, "RVI — radar oʻsimlik", "", "viridis", 0.0, 1.2, group_uz="Radar (SAR)"),
    "sar_water": LayerSpec(LayerKind.SAR_WATER, S1, "SAR suv niqobi (VV < −15 dB)", "", "mask", 0.0, 1.0, "mask", "Radar (SAR)"),
    "lst": LayerSpec(LayerKind.LST, LS, "Yer sirti harorati (LST)", "°C", "thermal", None, None, group_uz="Termal"),
    "landsat_ndvi": LayerSpec(LayerKind.LANDSAT_NDVI, LS, "Landsat NDVI", "", "veg", -0.2, 0.9, group_uz="Termal"),
    "elevation": LayerSpec(LayerKind.ELEVATION, DEM, "Balandlik", "m", "terrain", None, None, group_uz="Relyef"),
    "slope": LayerSpec(LayerKind.SLOPE, DEM, "Nishablik", "°", "slope", 0.0, 30.0, group_uz="Relyef"),
    "aspect": LayerSpec(LayerKind.ASPECT, DEM, "Aspekt (yon bagʻir yoʻnalishi)", "°", "cyclic", 0.0, 360.0, group_uz="Relyef"),
    "hillshade": LayerSpec(LayerKind.HILLSHADE, DEM, "Relyef soyasi", "", "gray", 0.0, 255.0, group_uz="Relyef"),
    "tri": LayerSpec(LayerKind.TRI, DEM, "TRI — gʻadir-budurlik", "m", "slope", 0.0, None, group_uz="Relyef"),
    "tpi": LayerSpec(LayerKind.TPI, DEM, "TPI — topografik joylashuv", "m", "diverge", -5.0, 5.0, group_uz="Relyef"),
    "depressions": LayerSpec(LayerKind.DEPRESSIONS, DEM, "Pastqamliklar", "", "mask", 0.0, 1.0, "mask", "Relyef"),
    "sm_surface": LayerSpec(LayerKind.SOIL_MOISTURE_SURFACE, SMAP, "Tuproq namligi (0–5 sm)", "m³/m³", "moist", 0.0, 0.5, group_uz="Tuproq namligi"),
    "sm_rootzone": LayerSpec(LayerKind.SOIL_MOISTURE_ROOTZONE, SMAP, "Tuproq namligi (ildiz qatlami)", "m³/m³", "moist", 0.0, 0.5, group_uz="Tuproq namligi"),
    "delta_ndvi": LayerSpec(LayerKind.DELTA_NDVI, S2, "ΔNDVI", "", "diverge_veg", -0.3, 0.3, group_uz="Oʻzgarishlar"),
    "delta_ndwi": LayerSpec(LayerKind.DELTA_NDWI, S2, "ΔNDWI", "", "diverge", -0.3, 0.3, group_uz="Oʻzgarishlar"),
    "delta_ndmi": LayerSpec(LayerKind.DELTA_NDMI, S2, "ΔNDMI", "", "diverge", -0.3, 0.3, group_uz="Oʻzgarishlar"),
    "delta_nbr": LayerSpec(LayerKind.DELTA_NBR, S2, "ΔNBR", "", "diverge_veg", -0.5, 0.5, group_uz="Oʻzgarishlar"),
    "delta_vv": LayerSpec(LayerKind.DELTA_VV, S1, "ΔVV", "dB", "diverge", -5.0, 5.0, group_uz="Oʻzgarishlar"),
    "class_change": LayerSpec(LayerKind.CLASS_CHANGE, DER, "Sinf oʻzgargan joylar", "", "change", 0.0, 1.0, "mask", "Oʻzgarishlar"),
}


def register_layer_spec(name: str, spec: LayerSpec) -> None:
    """ML/CV modellari o'z chiqish qatlamlarini katalogga qo'shadi (UI va API avtomatik ko'rsatadi)."""
    LAYER_SPECS[name] = spec


def _hex_to_rgba(h: str) -> tuple[int, int, int, int]:
    h = h.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    a = int(h[6:8], 16) if len(h) == 8 else 255
    return r, g, b, a


def _apply_palette(norm: np.ndarray, stops: list[str]) -> np.ndarray:
    """0–1 oralig'idagi qiymatlarni palitra bo'yicha chiziqli interpolyatsiya bilan RGBA ga o'tkazadi."""
    cols = np.array([_hex_to_rgba(s) for s in stops], dtype=np.float32)
    pos = np.clip(norm, 0.0, 1.0) * (len(stops) - 1)
    i0 = np.floor(pos).astype(np.int32)
    i1 = np.minimum(i0 + 1, len(stops) - 1)
    t = (pos - i0)[..., None]
    return (cols[i0] * (1 - t) + cols[i1] * t).astype(np.uint8)


def resolve_range(name: str, arr: np.ndarray) -> tuple[float | None, float | None]:
    """Qatlamning ko'rsatish oralig'i: qat'iy yoki ma'lumotdan (2–98 persentil)."""
    spec = LAYER_SPECS[name]
    vmin, vmax = spec.vmin, spec.vmax
    vals = arr[~np.isnan(arr)]
    if vals.size and (vmin is None or vmax is None):
        p2, p98 = np.percentile(vals, [2, 98])
        vmin = float(p2) if vmin is None else vmin
        vmax = float(p98) if vmax is None else vmax
        if vmax <= vmin:
            vmax = vmin + 1e-3
    return vmin, vmax


def legend_for(name: str, vmin: float | None, vmax: float | None) -> dict[str, Any]:
    """Frontend uchun afsona tavsifi."""
    spec = LAYER_SPECS[name]
    if spec.mode == "classes":
        return {
            "type": "classes",
            "items": [
                {"code": c, "label_uz": CLASS_LABELS_UZ[c], "color": CLASS_COLORS[c]}
                for c in CLASS_LABELS_UZ
                if c != CLASS_UNKNOWN
            ],
        }
    if spec.mode == "mask":
        return {
            "type": "classes",
            "items": [
                {"code": 1, "label_uz": "Ha", "color": PALETTES[spec.palette][1][:7]},
                {"code": 0, "label_uz": "Yoʻq", "color": "#80808060"},
            ],
        }
    if spec.mode == "rgb":
        return {"type": "rgb", "min": vmin, "max": vmax, "unit": "aks ettirish"}
    return {"type": "gradient", "stops": PALETTES[spec.palette], "min": vmin, "max": vmax, "unit": spec.unit}


def render_layer_png(name: str, arr: np.ndarray, output_path: Path) -> tuple[float | None, float | None]:
    """Bitta qatlamni shaffof PNG ga yozadi va ishlatilgan (vmin, vmax) ni qaytaradi."""
    spec = LAYER_SPECS[name]
    h, w = arr.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    valid = ~np.isnan(arr)
    vmin, vmax = resolve_range(name, arr)

    if spec.mode == "classes":
        codes = np.where(valid, arr, CLASS_UNKNOWN).astype(np.int32)
        for code, color in CLASS_COLORS.items():
            if code == CLASS_UNKNOWN:
                continue
            m = valid & (codes == code)
            if m.any():
                rgba[m] = _hex_to_rgba(color)
        # Noma'lum/bulut: yarim shaffof kulrang (AOI ichida, lekin sinf yo'q)
        unk = valid & (codes == CLASS_UNKNOWN)
        rgba[unk] = (90, 90, 90, 110)
    elif spec.mode == "mask":
        on = valid & (arr >= 0.5)
        off = valid & (arr < 0.5)
        rgba[on] = _hex_to_rgba(PALETTES[spec.palette][1])
        rgba[off] = (128, 128, 128, 60)
    elif valid.any() and vmin is not None and vmax is not None:
        norm = (np.where(valid, arr, vmin) - vmin) / (vmax - vmin)
        rgba[valid] = _apply_palette(norm[valid], PALETTES[spec.palette])

    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(output_path, format="PNG", optimize=False)
    return vmin, vmax


def render_composite_png(
    r: np.ndarray,
    g: np.ndarray,
    b: np.ndarray,
    output_path: Path,
    value_range: tuple[float, float] | None = None,
    aoi_mask: np.ndarray | None = None,
) -> tuple[float, float]:
    """Uch banddan RGB kompozit. value_range berilmasa — umumiy 2–98 persentil cho'zish."""
    valid = ~np.isnan(r) & ~np.isnan(g) & ~np.isnan(b)
    if aoi_mask is not None:
        valid &= aoi_mask
    if value_range is None:
        vals = np.concatenate([r[valid], g[valid], b[valid]]) if valid.any() else np.array([0.0, 1.0])
        lo, hi = (float(x) for x in np.percentile(vals, [2, 98]))
        if hi <= lo:
            hi = lo + 1e-3
    else:
        lo, hi = value_range
    rgba = np.zeros(r.shape + (4,), dtype=np.uint8)
    for i, band in enumerate((r, g, b)):
        norm = np.clip((np.where(valid, band, lo) - lo) / (hi - lo), 0.0, 1.0)
        rgba[..., i] = (norm * 255.0).astype(np.uint8)
    rgba[..., 3] = np.where(valid, 255, 0).astype(np.uint8)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(output_path, format="PNG")
    return lo, hi
