"""Standart analizatorlar implementatsiyasi va ro'yxatdan o'tkazilishi."""

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
from backend.app.analysis.formulas.rgb import (
    compute_brightness,
    compute_excess_green,
    compute_texture_std,
)
from backend.app.analysis.formulas.sar import (
    compute_rvi,
    compute_sar_water_mask,
    compute_vh_minus_vv,
    lee_filter_5x5,
)
from backend.app.analysis.formulas.terrain import (
    compute_depressions,
    compute_hillshade,
    compute_slope_and_aspect_horn,
    compute_tpi,
    compute_tri,
)
from backend.app.analysis.formulas.thermal import compute_landsat_lst_celsius
from backend.app.analysis.interface import AnalyzerInput, AnalyzerOutput
from backend.app.analysis.landcover import classify_landcover
from backend.app.analysis.registry import register_analyzer


def _calc_stats(arr: np.ndarray) -> dict[str, float]:
    """Massiv piksellari asosiy statistikasini hisoblaydi."""
    valid = arr[~np.isnan(arr)]
    if valid.size == 0:
        return {"mean": 0.0, "std": 0.0, "median": 0.0, "min": 0.0, "max": 0.0, "p10": 0.0, "p90": 0.0}
    return {
        "mean": float(np.mean(valid)),
        "std": float(np.std(valid)),
        "median": float(np.median(valid)),
        "min": float(np.min(valid)),
        "max": float(np.max(valid)),
        "p10": float(np.percentile(valid, 10)),
        "p90": float(np.percentile(valid, 90)),
    }


class IndicesAnalyzer:
    """Sentinel-2 spektral indekslari analizatori."""

    name = "indices"
    version = "rules-1.0"

    def run(self, data: AnalyzerInput) -> AnalyzerOutput:
        arrs = data.arrays
        b2 = arrs["B2"]
        b3 = arrs["B3"]
        b4 = arrs["B4"]
        b5 = arrs.get("B5", b4)
        b8 = arrs["B8"]
        b8a = arrs.get("B8A", b8)
        b11 = arrs["B11"]
        b12 = arrs["B12"]

        layers: dict[str, np.ndarray] = {
            "ndvi": compute_ndvi(b8, b4),
            "evi": compute_evi(b8, b4, b2),
            "ndre": compute_ndre(b8a, b5),
            "ndwi": compute_ndwi(b3, b8),
            "mndwi": compute_mndwi(b3, b11),
            "ndmi": compute_ndmi(b8, b11),
            "nbr": compute_nbr(b8, b12),
            "ndbi": compute_ndbi(b11, b8),
            "bsi": compute_bsi(b11, b4, b8, b2),
        }

        stats = {k: _calc_stats(v) for k, v in layers.items()}
        return AnalyzerOutput(layers=layers, stats=stats)


class SARAnalyzer:
    """Sentinel-1 SAR analizatori."""

    name = "sar"
    version = "rules-1.0"

    def run(self, data: AnalyzerInput) -> AnalyzerOutput:
        arrs = data.arrays
        vv = arrs["VV"]
        vh = arrs["VH"]

        vv_clean = lee_filter_5x5(vv)
        vh_clean = lee_filter_5x5(vh)

        layers: dict[str, np.ndarray] = {
            "vv": vv_clean,
            "vh": vh_clean,
            "vh_minus_vv": compute_vh_minus_vv(vh_clean, vv_clean),
            "rvi": compute_rvi(vh_clean, vv_clean),
            "water_mask": compute_sar_water_mask(vv_clean),
        }
        stats = {k: _calc_stats(v) for k, v in layers.items()}
        return AnalyzerOutput(layers=layers, stats=stats)


class TerrainAnalyzer:
    """Copernicus DEM relyef analizatori."""

    name = "terrain"
    version = "rules-1.0"

    def run(self, data: AnalyzerInput) -> AnalyzerOutput:
        dem = data.arrays["DEM"]
        slope, aspect = compute_slope_and_aspect_horn(dem, cell_size_m=data.pixel_size_m)
        hillshade = compute_hillshade(slope, aspect)
        tri = compute_tri(dem)
        tpi = compute_tpi(dem)
        depressions = compute_depressions(tpi, slope)

        layers: dict[str, np.ndarray] = {
            "elevation": dem,
            "slope": slope,
            "aspect": aspect,
            "hillshade": hillshade,
            "tri": tri,
            "tpi": tpi,
            "depressions": depressions,
        }
        stats = {k: _calc_stats(v) for k, v in layers.items()}
        return AnalyzerOutput(layers=layers, stats=stats)


class ThermalAnalyzer:
    """Landsat LST harorat analizatori."""

    name = "thermal"
    version = "rules-1.0"

    def run(self, data: AnalyzerInput) -> AnalyzerOutput:
        st_b10 = data.arrays["ST_B10"]
        lst_c = compute_landsat_lst_celsius(st_b10)
        layers = {"lst": lst_c}
        stats = {"lst": _calc_stats(lst_c)}
        return AnalyzerOutput(layers=layers, stats=stats)


class RGBAnalyzer:
    """RGB vizual va tekstura analizatori."""

    name = "rgb"
    version = "rules-1.0"

    def run(self, data: AnalyzerInput) -> AnalyzerOutput:
        b4 = data.arrays["B4"]  # Red
        b3 = data.arrays["B3"]  # Green
        b2 = data.arrays["B2"]  # Blue

        brightness = compute_brightness(b4, b3, b2)
        exg = compute_excess_green(b4, b3, b2)
        texture = compute_texture_std(brightness)

        layers = {"brightness": brightness, "exg": exg, "texture": texture}
        stats = {k: _calc_stats(v) for k, v in layers.items()}
        return AnalyzerOutput(layers=layers, stats=stats)


class LandcoverAnalyzer:
    """Yer qoplami va ishonchlilik analizatori."""

    name = "landcover"
    version = "rules-1.0"

    def run(self, data: AnalyzerInput) -> AnalyzerOutput:
        arrs = data.arrays
        extra = data.extra or {}

        classes, confidence = classify_landcover(
            ndvi=arrs["ndvi"],
            ndwi=arrs["ndwi"],
            mndwi=arrs["mndwi"],
            ndmi=arrs["ndmi"],
            bsi=arrs["bsi"],
            ndbi=arrs["ndbi"],
            nbr=arrs["nbr"],
            vv_db=arrs.get("vv"),
            vh_db=arrs.get("vh"),
            texture=arrs.get("texture"),
            depression_mask=arrs.get("depressions"),
            soil_moisture=arrs.get("soil_moisture"),
            cloud_mask=extra.get("cloud_mask"),
            s2_scl=extra.get("scl"),
            delta_nbr=extra.get("delta_nbr"),
        )

        layers = {
            "landcover": classes.astype(np.float32),
            "confidence": confidence,
        }
        stats = {
            "confidence": _calc_stats(confidence),
        }
        return AnalyzerOutput(layers=layers, stats=stats, metadata={"classes_uint8": classes})


def init_all_analyzers() -> None:
    """Barcha analizatorlarni registrga kiritadi."""
    register_analyzer(IndicesAnalyzer())
    register_analyzer(SARAnalyzer())
    register_analyzer(TerrainAnalyzer())
    register_analyzer(ThermalAnalyzer())
    register_analyzer(RGBAnalyzer())
    register_analyzer(LandcoverAnalyzer())


# Modul yuklanganda analizatorlarni avtomatik ro'yxatdan o'tkazish
init_all_analyzers()
