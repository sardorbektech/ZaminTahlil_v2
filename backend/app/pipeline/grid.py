"""Hudud geometriyasi (AOI), maydon hisobi va EPSG:3857 to'r (Grid) generatori."""

import math
from typing import Any

from backend.app.core.constants import DEFAULT_MAX_AOI_KM2
from backend.app.core.errors import AOIValidationError


def calculate_polygon_area_km2(coordinates: list[list[float]]) -> float:
    """WGS84 koordinatalaridagi ko'pburchak maydonini geodezik usulda (km²) hisoblaydi."""
    if len(coordinates) < 3:
        return 0.0

    # Sferik poligon maydoni (Girard teoremasi / Trapezoid integratsiyasi)
    earth_radius_m = 6378137.0
    area = 0.0

    for i in range(len(coordinates)):
        p1 = coordinates[i]
        p2 = coordinates[(i + 1) % len(coordinates)]
        lon1 = math.radians(p1[0])
        lat1 = math.radians(p1[1])
        lon2 = math.radians(p2[0])
        lat2 = math.radians(p2[1])
        area += (lon2 - lon1) * (2.0 + math.sin(lat1) + math.sin(lat2))

    area_m2 = abs(area * (earth_radius_m**2) / 2.0)
    return area_m2 / 1_000_000.0


def validate_aoi(aoi_geojson: dict[str, Any], max_area_km2: float = DEFAULT_MAX_AOI_KM2) -> float:
    """AOI GeoJSON geometriyasini tekshiradi va maydonini (km²) qaytaradi.

    Raises:
        AOIValidationError: Agar geometriya noto'g'ri yoki maydon chegaradan oshsa.
    """
    if not isinstance(aoi_geojson, dict):
        raise AOIValidationError("AOI GeoJSON obyekt boʻlishi kerak.")

    geom_type = aoi_geojson.get("type")
    coords = aoi_geojson.get("coordinates")

    if geom_type == "Polygon" and coords and isinstance(coords, list):
        outer_ring = coords[0]
        area_km2 = calculate_polygon_area_km2(outer_ring)
    else:
        raise AOIValidationError("Faqat Polygon tipidagi GeoJSON qoʻllab-quvvatlanadi.")

    if area_km2 <= 0.0:
        raise AOIValidationError("Hudud maydoni 0 dan katta boʻlishi kerak.")

    if area_km2 > max_area_km2:
        raise AOIValidationError(
            f"Hudud maydoni ({area_km2:.2f} km²) ruxsat etilgan maksimal chegaradan ({max_area_km2} km²) oshib ketdi."
        )

    return area_km2


def compute_grid_dimensions(
    aoi_geojson: dict[str, Any], resolution_m: float = 10.0
) -> tuple[int, int, float, list[float]]:
    """EPSG:3857 to'r o'lchamlarini (width, height, pixel_size_proj, bbox) hisoblaydi."""
    coords = aoi_geojson["coordinates"][0]
    lons = [c[0] for c in coords]
    lats = [c[1] for c in coords]

    min_lon, max_lon = min(lons), max(lons)
    min_lat, max_lat = min(lats), max(lats)
    center_lat = (min_lat + max_lat) / 2.0

    # EPSG:3857 metrlardagi koordinatalar
    def lon_to_x(lon: float) -> float:
        return lon * 20037508.34 / 180.0

    def lat_to_y(lat: float) -> float:
        y = math.log(math.tan((90.0 + lat) * math.pi / 360.0)) / (math.pi / 180.0)
        return y * 20037508.34 / 180.0

    min_x, max_x = lon_to_x(min_lon), lon_to_x(max_lon)
    min_y, max_y = lat_to_y(min_lat), lat_to_y(max_lat)

    # Pixel hajmi: res_m / cos(lat_center)
    cos_lat = max(math.cos(math.radians(center_lat)), 0.01)
    pixel_size_proj = resolution_m / cos_lat

    width = max(int((max_x - min_x) / pixel_size_proj), 10)
    height = max(int((max_y - min_y) / pixel_size_proj), 10)

    # 1024 dan oshib ketmasligi uchun tekshirish
    width = min(width, 1024)
    height = min(height, 1024)

    bbox_3857 = [min_x, min_y, max_x, max_y]
    return width, height, pixel_size_proj, bbox_3857
