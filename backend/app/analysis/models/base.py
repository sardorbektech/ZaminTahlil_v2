"""Klassik ML va CV modellari uchun bazaviy analizatorlar.

Ikkalasi ham Analyzer protokolini bajaradi, shuning uchun quvur ularni qoidaviy analizatorlar
kabi registrdan nomi bilan oladi. Model natijasi NaN bo'lgan joylar "maʼlumot yoʻq" bo'lib qoladi.
"""

from typing import Any

import numpy as np

from backend.app.analysis.interface import AnalyzerInput, AnalyzerOutput
from backend.app.analysis.models.features import build_feature_stack, build_image_tensor, unflatten
from backend.app.analysis.registry import register_analyzer


def _stats(arr: np.ndarray, aoi: np.ndarray | None) -> dict[str, Any]:
    from backend.app.analysis.analyzers import calc_stats

    return calc_stats(arr, aoi)


class _ModelBase:
    name = "model"
    version = "0"
    method = "classic_ml"
    stage = "s2_observation"
    slot: str | None = "extra"
    inputs: list[str] = []
    output_specs: dict[str, Any] = {}  # {qatlam_nomi: render.LayerSpec}
    _loaded = False

    def load(self) -> None:
        """Model og'irliklarini yuklash (birinchi chaqiriqda bir marta). Meros oluvchi qayta yozadi."""

    def _ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()
            self._loaded = True


class PixelModelAnalyzer(_ModelBase):
    """Klassik ML: har bir piksel belgi vektori (masalan, Random Forest, GBM, SVM).

    `predict_pixels(X)` qaytaradi:
      - (N,) — bitta qatlam (sinf kodi yoki qiymat) yoki
      - (N, K) — ehtimollar; unda qatlam = argmax, ishonchlilik = max ehtimol.
    """

    method = "classic_ml"

    def predict_pixels(self, x: np.ndarray) -> np.ndarray:  # pragma: no cover - meros oluvchida
        raise NotImplementedError

    def run(self, data: AnalyzerInput) -> AnalyzerOutput:
        self._ensure_loaded()
        x, valid = build_feature_stack(data.arrays, self.inputs, data.aoi_mask)
        out_name = next(iter(self.output_specs))
        if x.shape[0] == 0:
            layer = np.full(valid.shape, np.nan, np.float32)
            return AnalyzerOutput({out_name: layer}, {out_name: _stats(layer, data.aoi_mask)})
        pred = np.asarray(self.predict_pixels(x))
        conf = None
        if pred.ndim == 2:
            conf = unflatten(pred.max(axis=1), valid)
            pred = pred.argmax(axis=1)
        layer = unflatten(pred, valid)
        return AnalyzerOutput(
            layers={out_name: layer},
            stats={out_name: _stats(layer, data.aoi_mask)},
            confidence=conf,
            metadata={"classes": np.nan_to_num(layer, nan=0).astype(np.uint8)} if self.slot == "landcover" else {},
        )


class ImageModelAnalyzer(_ModelBase):
    """Computer vision: (C × H × W) tensor bo'yicha segmentatsiya yoki obyekt aniqlash.

    `predict_image(tensor, valid)` qaytaradi: {qatlam_nomi: H × W massiv}. Katta to'rlarni
    bo'laklab ishlash (tiling) meros oluvchining vazifasi.
    """

    method = "cv"

    def predict_image(self, tensor: np.ndarray, valid: np.ndarray) -> dict[str, np.ndarray]:  # pragma: no cover
        raise NotImplementedError

    def run(self, data: AnalyzerInput) -> AnalyzerOutput:
        self._ensure_loaded()
        tensor, valid = build_image_tensor(data.arrays, self.inputs)
        if data.aoi_mask is not None:
            valid &= data.aoi_mask.astype(bool)
        raw = self.predict_image(tensor, valid)
        layers = {k: np.where(valid, v, np.nan).astype(np.float32) for k, v in raw.items()}
        return AnalyzerOutput(layers=layers, stats={k: _stats(v, data.aoi_mask) for k, v in layers.items()})


def register_model(model: Any) -> None:
    """Modelni analizatorlar registriga va uning qatlamlarini render katalogiga qo'shadi."""
    from backend.app.pipeline.render import register_layer_spec

    for lname, spec in model.output_specs.items():
        register_layer_spec(lname, spec)
    register_analyzer(model)
