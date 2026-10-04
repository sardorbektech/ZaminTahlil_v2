"""Hudud (AOI) tekshiruvi, maydon hisobi va EPSG:3857 to'ri.

To'r Leaflet bilan aynan mos kelishi uchun EPSG:3857 da quriladi.
Proyeksiyadagi piksel o'lchami = res_m / cos(markaz kengligi); yerdagi haqiqiy o'lcham = res_m.
"""

import json
import math
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from backend.app.core import constants as C
from backend.app.core.errors import AOIValidationError

Ring = list[list[float]]


# ---------------------------------------------------------------------------
# Proyeksiya yordamchilari (sferik Mercator, EPSG:3857)
# ---------------------------------------------------------------------------
def lon_to_x(lon: float) -> float:
    """Uzunlikni EPSG:3857 X (metr) ga o'tkazadi."""
    return lon * C.WEB_MERCATOR_HALF / 180.0


def lat_to_y(lat: float) -> float:
    """Kenglikni EPSG:3857 Y (metr) ga o'tkazadi."""
    return math.log(math.tan((90.0 + lat) * math.pi / 360.0)) * C.EARTH_RADIUS_M


def x_to_lon(x: float) -> float:
    """EPSG:3857 X ni uzunlikka o'tkazadi."""
    return x * 180.0 / C.WEB_MERCATOR_HALF


def y_to_lat(y: float) -> float:
    """EPSG:3857 Y ni kenglikka o'tkazadi."""
    return math.degrees(2.0 * math.atan(math.exp(y / C.EARTH_RADIUS_M)) - math.pi / 2.0)


# ---------------------------------------------------------------------------
# AOI tekshiruvi
# ---------------------------------------------------------------------------
def ring_area_km2(ring: Ring) -> float:
    """WGS84 halqasining sferadagi maydoni (km²), trapetsiya integrali bo'yicha."""
    if len(ring) < 3:
        return 0.0
    area = 0.0
    n = len(ring)
    for i in range(n):
        lon1, lat1 = math.radians(ring[i][0]), math.radians(ring[i][1])
        lon2, lat2 = math.radians(ring[(i + 1) % n][0]), math.radians(ring[(i + 1) % n][1])
        area += (lon2 - lon1) * (2.0 + math.sin(lat1) + math.sin(lat2))
    return abs(area * C.EARTH_RADIUS_M**2 / 2.0) / 1_000_000.0


def calculate_polygon_area_km2(coordinates: Ring) -> float:
    """Orqaga moslik uchun: tashqi halqa maydoni (km²)."""
    return ring_area_km2(coordinates)


def _segments_intersect(p1: list[float], p2: list[float], p3: list[float], p4: list[float]) -> bool:
    def orient(a: list[float], b: list[float], c: list[float]) -> float:
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    d1, d2 = orient(p3, p4, p1), orient(p3, p4, p2)
    d3, d4 = orient(p1, p2, p3), orient(p1, p2, p4)
    return (d1 * d2 < 0) and (d3 * d4 < 0)


def _ring_self_intersects(ring: Ring) -> bool:
    pts = ring[:-1]
    n = len(pts)
    for i in range(n):
        a1, a2 = pts[i], pts[(i + 1) % n]
        for j in range(i + 1, n):
            if abs(i - j) <= 1 or (i == 0 and j == n - 1):
                continue
            if _segments_intersect(a1, a2, pts[j], pts[(j + 1) % n]):
                return True
    return False


def _clean_ring(raw: Any) -> Ring:
    if not isinstance(raw, list) or len(raw) < 3:
        raise AOIValidationError("Koʻpburchak halqasida kamida 3 ta nuqta boʻlishi kerak.")
    ring: Ring = []
    for pt in raw:
        if not isinstance(pt, list | tuple) or len(pt) < 2:
            raise AOIValidationError("Koordinata [uzunlik, kenglik] shaklida boʻlishi kerak.")
        lon, lat = float(pt[0]), float(pt[1])
        if not (math.isfinite(lon) and math.isfinite(lat)) or not (-180 <= lon <= 180) or not (-85 <= lat <= 85):
            raise AOIValidationError("Koordinatalar ruxsat etilgan oraliqdan tashqarida.")
        ring.append([lon, lat])
    if ring[0] != ring[-1]:
        ring.append(list(ring[0]))
    if len({(p[0], p[1]) for p in ring}) < 3:
        raise AOIValidationError("Koʻpburchak nuqtalari bir-biridan farq qilishi kerak.")
    return ring


def normalize_aoi(aoi: dict[str, Any]) -> dict[str, Any]:
    """GeoJSON (Feature yoki Polygon) ni yopiq halqali Polygon geometriyasiga keltiradi."""
    if not isinstance(aoi, dict):
        raise AOIValidationError("AOI GeoJSON obyekt boʻlishi kerak.")
    geom = aoi.get("geometry") if aoi.get("type") == "Feature" else aoi
    if not isinstance(geom, dict) or geom.get("type") != "Polygon":
        raise AOIValidationError("Faqat Polygon turidagi GeoJSON qoʻllab-quvvatlanadi.")
    coords = geom.get("coordinates")
    if not isinstance(coords, list) or not coords:
        raise AOIValidationError("Polygon koordinatalari boʻsh.")
    rings = [_clean_ring(r) for r in coords]
    for r in rings:
        if _ring_self_intersects(r):
            raise AOIValidationError("Koʻpburchak chiziqlari oʻzaro kesishmasligi kerak.")
    return {"type": "Polygon", "coordinates": rings}


def aoi_area_km2(aoi: dict[str, Any]) -> float:
    """Normallashtirilgan Polygon maydoni (teshiklar ayirilgan)."""
    rings = aoi["coordinates"]
    return max(0.0, ring_area_km2(rings[0]) - sum(ring_area_km2(r) for r in rings[1:]))


def validate_aoi(aoi_geojson: dict[str, Any], max_area_km2: float = C.DEFAULT_MAX_AOI_KM2) -> float:
    """AOI ni tekshiradi va maydonini (km²) qaytaradi.

    Raises:
        AOIValidationError: geometriya noto'g'ri yoki maydon chegaradan oshsa.
    """
    aoi = normalize_aoi(aoi_geojson)
    area = aoi_area_km2(aoi)
    if area <= 0.0:
        raise AOIValidationError("Hudud maydoni 0 dan katta boʻlishi kerak.")
    if area > max_area_km2:
        raise AOIValidationError(
            f"Hudud maydoni ({area:.2f} km²) ruxsat etilgan chegaradan ({max_area_km2:g} km²) katta."
        )
    return area


# ---------------------------------------------------------------------------
# To'r (Grid)
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Grid:
    """EPSG:3857 to'ri: chap-yuqori burchak, piksel o'lchami va o'lchamlar."""

    min_x: float
    max_y: float
    pixel_size: float  # proyeksiya birligida (m)
    width: int
    height: int
    res_m: float  # yerdagi nominal o'lcham

    @property
    def max_x(self) -> float:
        return self.min_x + self.width * self.pixel_size

    @property
    def min_y(self) -> float:
        return self.max_y - self.height * self.pixel_size

    def bounds_latlon(self) -> list[list[float]]:
        """Leaflet uchun [[janub, g'arb], [shimol, sharq]] chegaralari."""
        return [
            [y_to_lat(self.min_y), x_to_lon(self.min_x)],
            [y_to_lat(self.max_y), x_to_lon(self.max_x)],
        ]

    def affine(self, col0: int = 0, row0: int = 0) -> dict[str, float]:
        """GEE computePixels uchun affine transformatsiya (bo'lak siljishi bilan)."""
        return {
            "scaleX": self.pixel_size,
            "shearX": 0.0,
            "translateX": self.min_x + col0 * self.pixel_size,
            "shearY": 0.0,
            "scaleY": -self.pixel_size,
            "translateY": self.max_y - row0 * self.pixel_size,
        }

    def pixel_of(self, lon: float, lat: float) -> tuple[int, int] | None:
        """(lon, lat) nuqtasi tushgan (qator, ustun); to'rdan tashqarida bo'lsa None."""
        col = math.floor((lon_to_x(lon) - self.min_x) / self.pixel_size)
        row = math.floor((self.max_y - lat_to_y(lat)) / self.pixel_size)
        if 0 <= row < self.height and 0 <= col < self.width:
            return row, col
        return None

    def row_pixel_area_m2(self) -> np.ndarray:
        """Har bir qator uchun pikselning yerdagi maydoni (m²): (p·cos φ)²."""
        ys = self.max_y - (np.arange(self.height) + 0.5) * self.pixel_size
        lats = np.degrees(2.0 * np.arctan(np.exp(ys / C.EARTH_RADIUS_M)) - np.pi / 2.0)
        ground = self.pixel_size * np.cos(np.radians(lats))
        return (ground**2).astype(np.float64)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["bounds_latlon"] = self.bounds_latlon()
        d["crs"] = "EPSG:3857"
        return d

    def to_json(self) -> str:
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, s: str) -> "Grid":
        d = json.loads(s)
        return cls(
            min_x=d["min_x"],
            max_y=d["max_y"],
            pixel_size=d["pixel_size"],
            width=d["width"],
            height=d["height"],
            res_m=d["res_m"],
        )


def build_grid(aoi: dict[str, Any], resolution_m: float) -> Grid:
    """AOI qamrovchi to'rni quradi (piksellar butun sonli, chegaralar piksel bo'yicha tekislanadi)."""
    outer = aoi["coordinates"][0]
    lons = [p[0] for p in outer]
    lats = [p[1] for p in outer]
    center_lat = (min(lats) + max(lats)) / 2.0
    pixel = resolution_m / math.cos(math.radians(center_lat))

    min_x, max_x = lon_to_x(min(lons)), lon_to_x(max(lons))
    min_y, max_y = lat_to_y(min(lats)), lat_to_y(max(lats))
    # Piksel chegaralarini global to'rga tekislash (bir xil AOI — bir xil to'r)
    min_x = math.floor(min_x / pixel) * pixel
    max_y = math.ceil(max_y / pixel) * pixel
    width = max(1, math.ceil((max_x - min_x) / pixel))
    height = max(1, math.ceil((max_y - min_y) / pixel))
    if width * height > C.MAX_GRID_PIXELS:
        raise AOIValidationError(
            "Hudud chegaralovchi toʻrtburchagi juda katta. Aniqlikni pasaytiring yoki hududni kichraytiring."
        )
    return Grid(min_x=min_x, max_y=max_y, pixel_size=pixel, width=width, height=height, res_m=resolution_m)


def compute_grid_dimensions(
    aoi_geojson: dict[str, Any], resolution_m: float = 10.0
) -> tuple[int, int, float, list[float]]:
    """Orqaga moslik: (width, height, pixel_size, bbox_3857)."""
    g = build_grid(normalize_aoi(aoi_geojson), resolution_m)
    return g.width, g.height, g.pixel_size, [g.min_x, g.min_y, g.max_x, g.max_y]


def rasterize_aoi(aoi: dict[str, Any], grid: Grid) -> np.ndarray:
    """AOI ni to'rga rasterlaydi: True — AOI ichida (teshiklar chiqarib tashlangan)."""
    img = Image.new("L", (grid.width, grid.height), 0)
    draw = ImageDraw.Draw(img)
    for i, ring in enumerate(aoi["coordinates"]):
        pts = [
            ((lon_to_x(lon) - grid.min_x) / grid.pixel_size, (grid.max_y - lat_to_y(lat)) / grid.pixel_size)
            for lon, lat in ring
        ]
        draw.polygon(pts, fill=255 if i == 0 else 0, outline=255 if i == 0 else 0)
    return np.asarray(img, dtype=np.uint8) > 0
