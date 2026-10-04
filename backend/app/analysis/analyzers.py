"""Standart (qoidaviy) analizatorlar va ularni registrga kiritish.

Har bir analizator sof hisoblash bajaradi: I/O yo'q, float32 massivlar, NaN — yaroqsiz piksel.
"""

from typing import Any

import numpy as np

from backend.app.analysis.changes import (
    class_change_mask,
    compute_class_transitions,
    compute_delta_array,
)
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
from backend.app.analysis.formulas.sar import (
    compute_rvi,
    compute_sar_water_mask,
    compute_vh_minus_vv,
    lee_filter_db,
)
from backend.app.analysis.formulas.terrain import (
    compute_depressions,
    compute_hillshade,
    compute_slope_and_aspect_horn,
    compute_tpi,
    compute_tri,
)
from backend.app.analysis.formulas.thermal import (
    compute_landsat_lst_celsius,
    landsat_qa_invalid_mask,
)
from backend.app.analysis.interface import AnalyzerInput, AnalyzerOutput
from backend.app.analysis.landcover import classify_landcover
from backend.app.analysis.registry import register_analyzer
from backend.app.core import constants as C

VERSION = "rules-1.0"


def calc_stats(arr: np.ndarray, aoi_mask: np.ndarray | None = None) -> dict[str, Any]:
    """AOI ichidagi yaroqli piksellar statistikasi. Yaroqli piksel bo'lmasa qiymatlar None (0 emas)."""
    sel = ~np.isnan(arr)
    if aoi_mask is not None:
        sel &= aoi_mask.astype(bool)
    vals = arr[sel].astype(np.float64)
    if vals.size == 0:
        return {"count": 0, "mean": None, "std": None, "median": None, "min": None, "max": None, "p10": None, "p90": None}
    p10, med, p90 = np.percentile(vals, [10, 50, 90])
    return {
        "count": int(vals.size),
        "mean": float(vals.mean()),
        "std": float(vals.std()),
        "median": float(med),
        "min": float(vals.min()),
        "max": float(vals.max()),
        "p10": float(p10),
        "p90": float(p90),
    }


def _stats_all(layers: dict[str, np.ndarray], aoi: np.ndarray | None) -> dict[str, dict[str, Any]]:
    return {k: calc_stats(v, aoi) for k, v in layers.items()}


class IndicesAnalyzer:
    """Sentinel-2 spektral indekslari (§7.2). Kirish: niqoblangan B2, B3, B4, B5, B8, B8A, B11, B12."""

    name = "indices"
    version = VERSION

    def run(self, data: AnalyzerInput) -> AnalyzerOutput:
        a = data.arrays
        layers = {
            "ndvi": compute_ndvi(a["B8"], a["B4"]),
            "evi": compute_evi(a["B8"], a["B4"], a["B2"]),
            "ndre": compute_ndre(a["B8A"], a["B5"]),
            "ndwi": compute_ndwi(a["B3"], a["B8"]),
            "mndwi": compute_mndwi(a["B3"], a["B11"]),
            "ndmi": compute_ndmi(a["B8"], a["B11"]),
            "nbr": compute_nbr(a["B8"], a["B12"]),
            "ndbi": compute_ndbi(a["B11"], a["B8"]),
            "bsi": compute_bsi(a["B11"], a["B4"], a["B8"], a["B2"]),
        }
        return AnalyzerOutput(layers=layers, stats=_stats_all(layers, data.aoi_mask))


class RGBAnalyzer:
    """RGB xususiyatlari (§7.3): yorqinlik, xromatiklik, ExG, tekstura. Kirish: B4, B3, B2."""

    name = "rgb"
    version = VERSION

    def run(self, data: AnalyzerInput) -> AnalyzerOutput:
        r, g, b = data.arrays["B4"], data.arrays["B3"], data.arrays["B2"]
        brightness = compute_brightness(r, g, b)
        layers = {
            "brightness": brightness,
            "chroma_green": compute_chromaticity_green(r, g, b),
            "exg": compute_excess_green(r, g, b),
            "texture": compute_texture_std(brightness),
        }
        return AnalyzerOutput(layers=layers, stats=_stats_all(layers, data.aoi_mask))


class SARAnalyzer:
    """Sentinel-1 (§7.3): Lee 5x5 (chiziqli birlikda), VV/VH dB, VH−VV, RVI, suv niqobi."""

    name = "sar"
    version = VERSION

    def run(self, data: AnalyzerInput) -> AnalyzerOutput:
        vv = lee_filter_db(data.arrays["VV"])
        vh = lee_filter_db(data.arrays["VH"])
        layers = {
            "vv": vv,
            "vh": vh,
            "vh_minus_vv": compute_vh_minus_vv(vh, vv),
            "rvi": compute_rvi(vh, vv),
            "sar_water": compute_sar_water_mask(vv),
        }
        return AnalyzerOutput(layers=layers, stats=_stats_all(layers, data.aoi_mask))


class TerrainAnalyzer:
    """Copernicus DEM relyefi (§7.3): balandlik, nishablik, aspekt, hillshade, TRI, TPI, pastqamliklar."""

    name = "terrain"
    version = VERSION

    def run(self, data: AnalyzerInput) -> AnalyzerOutput:
        dem = data.arrays["DEM"]
        slope, aspect = compute_slope_and_aspect_horn(dem, cell_size_m=data.pixel_size_m)
        tpi = compute_tpi(dem)
        layers = {
            "elevation": dem.astype(np.float32),
            "slope": slope,
            "aspect": aspect,
            "hillshade": compute_hillshade(slope, aspect),
            "tri": compute_tri(dem),
            "tpi": tpi,
            "depressions": compute_depressions(tpi, slope),
        }
        return AnalyzerOutput(layers=layers, stats=_stats_all(layers, data.aoi_mask))


class ThermalAnalyzer:
    """Landsat (§7.3): LST °C (ST_B10) va kesishgan tekshiruv uchun Landsat NDVI (SR_B5, SR_B4).

    QA_PIXEL bo'yicha bulut/soya/fill piksellari NaN qilinadi.
    """

    name = "thermal"
    version = VERSION

    def run(self, data: AnalyzerInput) -> AnalyzerOutput:
        a = data.arrays
        invalid = landsat_qa_invalid_mask(a["QA_PIXEL"])
        st = np.where(invalid, np.nan, a["ST_B10"]).astype(np.float32)
        red = np.where(invalid, np.nan, a["SR_B4"]).astype(np.float32)
        nir = np.where(invalid, np.nan, a["SR_B5"]).astype(np.float32)
        layers = {"lst": compute_landsat_lst_celsius(st), "landsat_ndvi": compute_ndvi(nir, red)}
        cloud = invalid & ~np.isnan(a["QA_PIXEL"])
        return AnalyzerOutput(
            layers=layers, stats=_stats_all(layers, data.aoi_mask), metadata={"cloud_mask": cloud}
        )


class SoilMoistureAnalyzer:
    """SMAP L4 tuproq namligi (§7.3): qiymatlar va trend (vaqt qatori bo'yicha chiziqli moyillik).

    Trend formulasi: eng kichik kvadratlar bo'yicha sm(t) = a + b·t; b — m³/m³ kuniga.
    """

    name = "soil_moisture"
    version = VERSION

    def run(self, data: AnalyzerInput) -> AnalyzerOutput:
        layers = {
            "sm_surface": data.arrays["sm_surface"].astype(np.float32),
            "sm_rootzone": data.arrays["sm_rootzone"].astype(np.float32),
        }
        series = data.extra.get("series") or []
        trend: dict[str, Any] = {"available": False}
        pts = [(r["ts"], r["sm_surface"]) for r in series if r.get("sm_surface") is not None]
        if len(pts) >= 2:
            t = np.array([p[0] for p in pts], dtype=np.float64) / 86400.0
            y = np.array([p[1] for p in pts], dtype=np.float64)
            slope = float(np.polyfit(t - t[0], y, 1)[0]) if np.ptp(t) > 0 else None
            trend = {
                "available": True,
                "first_ts": pts[0][0],
                "last_ts": pts[-1][0],
                "first": float(y[0]),
                "last": float(y[-1]),
                "delta": float(y[-1] - y[0]),
                "slope_per_day": slope,
                "n": len(pts),
            }
        return AnalyzerOutput(
            layers=layers, stats=_stats_all(layers, data.aoi_mask), metadata={"trend": trend}
        )


class LandcoverAnalyzer:
    """Qoidaviy yer qoplami (§7.4) va har bir piksel uchun ishonchlilik.

    Slot "landcover": sozlamalardagi `landcover_analyzer` orqali ML/CV modeli bilan almashtiriladi.
    """

    name = "landcover"
    version = VERSION
    method = "rules"
    stage = "s2_observation"
    slot = "landcover"

    def run(self, data: AnalyzerInput) -> AnalyzerOutput:
        a, ex = data.arrays, data.extra
        classes, conf = classify_landcover(
            ndvi=a["ndvi"],
            ndwi=a["ndwi"],
            mndwi=a["mndwi"],
            ndmi=a["ndmi"],
            bsi=a["bsi"],
            ndbi=a["ndbi"],
            nbr=a["nbr"],
            vv_db=a.get("vv"),
            vh_db=a.get("vh"),
            texture=a.get("texture"),
            depression_mask=a.get("depressions"),
            soil_moisture=a.get("sm_surface"),
            cloud_mask=ex.get("cloud_mask"),
            s2_scl=ex.get("scl"),
            delta_nbr=ex.get("delta_nbr"),
        )
        if data.aoi_mask is not None:
            classes = np.where(data.aoi_mask, classes, C.CLASS_UNKNOWN).astype(np.uint8)
        conf_layer = np.where(classes == C.CLASS_UNKNOWN, np.nan, conf).astype(np.float32)
        lc_layer = classes.astype(np.float32)
        if data.aoi_mask is not None:
            lc_layer[~data.aoi_mask] = np.nan
            conf_layer[~data.aoi_mask] = np.nan
        layers = {"landcover": lc_layer, "confidence": conf_layer}
        return AnalyzerOutput(
            layers=layers,
            stats={"confidence": calc_stats(conf_layer, data.aoi_mask)},
            confidence=conf_layer,
            metadata={"classes": classes},
        )


class ChangeAnalyzer:
    """Ikki ketma-ket haqiqiy kuzatuv orasidagi o'zgarishlar (§7.5).

    Kirish: arrays — joriy qatlamlar, extra["previous"] — oldingi qatlamlar (bir xil nomlar),
    extra["names"] — farqi olinadigan qatlam nomlari, ixtiyoriy extra["classes"]/["prev_classes"].
    """

    name = "change"
    version = VERSION

    def run(self, data: AnalyzerInput) -> AnalyzerOutput:
        prev: dict[str, np.ndarray] = data.extra["previous"]
        layers: dict[str, np.ndarray] = {}
        for n in data.extra.get("names", []):
            if n in data.arrays and n in prev:
                layers[f"delta_{n}"] = compute_delta_array(data.arrays[n], prev[n])
        meta: dict[str, Any] = {}
        cur_cls, prev_cls = data.extra.get("classes"), data.extra.get("prev_classes")
        if cur_cls is not None and prev_cls is not None:
            meta["transitions"] = compute_class_transitions(cur_cls, prev_cls, data.aoi_mask)
            chg = class_change_mask(cur_cls, prev_cls)
            if data.aoi_mask is not None:
                chg[~data.aoi_mask] = np.nan
            layers["class_change"] = chg
        return AnalyzerOutput(layers=layers, stats=_stats_all(layers, data.aoi_mask), metadata=meta)


def init_all_analyzers() -> None:
    """Barcha analizatorlarni (qoidaviy va yoqilgan ML/CV modellarini) registrga kiritadi."""
    for an in (
        IndicesAnalyzer(),
        RGBAnalyzer(),
        SARAnalyzer(),
        TerrainAnalyzer(),
        ThermalAnalyzer(),
        SoilMoistureAnalyzer(),
        LandcoverAnalyzer(),
        ChangeAnalyzer(),
    ):
        register_analyzer(an)
    import importlib

    from backend.app.analysis.models import ENABLED_MODELS

    for mod in ENABLED_MODELS:  # har bir modul import qilinganda o'zini register_model() bilan qo'shadi
        importlib.import_module(mod)
