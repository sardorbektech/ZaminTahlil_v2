"""Relyef (DEM) morfometriyasi formulalari moduli.

Copernicus DEM (30m) orqali Horn usulida nishablik va aspekt,
hillshade, TRI, TPI hamda pastqamliklarni (depressions) hisoblash.
"""

import numpy as np
from scipy.ndimage import uniform_filter


def compute_slope_and_aspect_horn(
    dem: np.ndarray, cell_size_m: float = 30.0
) -> tuple[np.ndarray, np.ndarray]:
    """Horn (1981) usuli bo'yicha relyef nishabligi (darajada) va aspektini (azimut) hisoblaydi.

    Formula:
        3x3 darcha:
        [a, b, c]
        [d, e, f]
        [g, h, i]
        dz/dx = ((c + 2*f + i) - (a + 2*d + g)) / (8 * cell_size)
        dz/dy = ((g + 2*h + i) - (a + 2*b + c)) / (8 * cell_size)
        slope = arctan(sqrt((dz/dx)^2 + (dz/dy)^2)) * (180 / pi)
        aspect = compass azimut (0 = Shimol, 90 = Sharq, 180 = Janub, 270 = G'arb)
    """
    rows, cols = dem.shape
    slope = np.full((rows, cols), np.nan, dtype=np.float32)
    aspect = np.full((rows, cols), np.nan, dtype=np.float32)

    # 3x3 darchalar uchun ichki massivlar
    a = dem[:-2, :-2]
    b = dem[:-2, 1:-1]
    c = dem[:-2, 2:]
    d = dem[1:-1, :-2]
    f = dem[1:-1, 2:]
    g = dem[2:, :-2]
    h = dem[2:, 1:-1]
    i = dem[2:, 2:]

    dz_dx = ((c + 2.0 * f + i) - (a + 2.0 * d + g)) / (8.0 * cell_size_m)
    dz_dy = ((g + 2.0 * h + i) - (a + 2.0 * b + c)) / (8.0 * cell_size_m)

    slope_rad = np.arctan(np.sqrt(dz_dx**2 + dz_dy**2))
    slope_deg = np.degrees(slope_rad)
    slope[1:-1, 1:-1] = slope_deg

    aspect_rad = np.arctan2(dz_dy, -dz_dx)
    aspect_deg = np.degrees(aspect_rad)
    compass_aspect = (450.0 - aspect_deg) % 360.0
    aspect[1:-1, 1:-1] = compass_aspect

    return slope.astype(np.float32), aspect.astype(np.float32)


def compute_hillshade(
    slope_deg: np.ndarray,
    aspect_deg: np.ndarray,
    azimuth_deg: float = 315.0,
    altitude_deg: float = 45.0,
) -> np.ndarray:
    """Relyefning soya-yorug'lik modeli (Hillshade).

    Formula:
        zenith_rad = radians(90 - altitude_deg)
        azimuth_rad = radians(azimuth_deg)
        shade = 255 * (cos(zenith) * cos(slope) + sin(zenith) * sin(slope) * cos(azimuth - aspect))
    Standart parametrlar: Azimut 315° (Shimoli-g'arb), quyosh balandligi 45°.
    """
    zenith_rad = np.radians(90.0 - altitude_deg)
    azimuth_math = np.radians((360.0 - azimuth_deg + 90.0) % 360.0)

    slope_rad = np.radians(slope_deg)
    aspect_rad = np.radians((360.0 - aspect_deg + 90.0) % 360.0)

    with np.errstate(invalid="ignore"):
        cos_inc = np.cos(zenith_rad) * np.cos(slope_rad) + np.sin(zenith_rad) * np.sin(
            slope_rad
        ) * np.cos(azimuth_math - aspect_rad)
        shade = np.clip(255.0 * cos_inc, 0.0, 255.0)
    return shade.astype(np.float32)


def compute_tri(dem: np.ndarray) -> np.ndarray:
    """Relyef g'adir-budurlik indeksi (Terrain Ruggedness Index - Riley et al.).

    Formula: 3x3 darcha markaziy pikseli va uning 8 ta qo'shnisi o'rtasidagi
    balandlik farqlari kvadratlarining yig'indisining kvadrat ildizi.
    """
    rows, cols = dem.shape
    tri = np.full((rows, cols), np.nan, dtype=np.float32)

    e = dem[1:-1, 1:-1]
    neighbors = [
        dem[:-2, :-2],
        dem[:-2, 1:-1],
        dem[:-2, 2:],
        dem[1:-1, :-2],
        dem[1:-1, 2:],
        dem[2:, :-2],
        dem[2:, 1:-1],
        dem[2:, 2:],
    ]
    sq_diff_sum = np.zeros_like(e, dtype=np.float32)
    for n in neighbors:
        sq_diff_sum += (n - e) ** 2

    tri[1:-1, 1:-1] = np.sqrt(sq_diff_sum)
    return tri.astype(np.float32)


def compute_tpi(dem: np.ndarray, size: int = 5) -> np.ndarray:
    """Topografik joylashuv indeksi (Topographic Position Index - TPI).

    Formula: Piksel balandligi va uning atrofidagi (5x5 darcha) o'rtacha balandlik farqi.
    Manfiy qiymatlar: pastqamliklar, vodiylar; Musbat qiymatlar: tepaliklar, tizmali cho'qqilar.
    """
    valid = ~np.isnan(dem)
    filled = np.where(valid, dem, np.nanmean(dem))
    mean_local = uniform_filter(filled, size=size, mode="reflect")
    tpi = dem - mean_local
    return np.where(valid, tpi, np.nan).astype(np.float32)


def compute_depressions(tpi: np.ndarray, slope_deg: np.ndarray) -> np.ndarray:
    """Suv to'planishi va botqoqlik ehtimoli yuqori bo'lgan pastqamliklar (Depressions).

    Formula: TPI < -1.0 (mahalliy chuqurlik) va Slope < 3.0° (tekis pastlik).
    """
    with np.errstate(invalid="ignore"):
        mask = (tpi < -1.0) & (slope_deg < 3.0)
    return mask.astype(np.float32)
