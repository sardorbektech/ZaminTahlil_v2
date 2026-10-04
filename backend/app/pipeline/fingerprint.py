"""Barmoq izi (fingerprint) hisoblash va deduplikatsiya moduli."""

import hashlib
import json
from typing import Any


def compute_recon_fingerprint(
    aoi_geojson: dict[str, Any], scene_ids: list[str]
) -> bytes:
    """Normallashtirilgan geometriya va tartiblangan scene ID'lari bo'yicha 32-baytli SHA-256 xesh yaratadi."""
    coords = aoi_geojson.get("coordinates", [])

    # Geometriyani yaxlitlash orqali normallashtirish (6 ta o'nlik belgigacha)
    def _round_coords(obj: Any) -> Any:
        if isinstance(obj, list):
            return [_round_coords(x) for x in obj]
        if isinstance(obj, float):
            return round(obj, 6)
        return obj

    norm_coords = _round_coords(coords)
    sorted_scenes = sorted(scene_ids)

    payload = {
        "coordinates": norm_coords,
        "scenes": sorted_scenes,
    }

    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(serialized).digest()
