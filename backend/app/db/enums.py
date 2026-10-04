"""Ma'lumotlar bazasi uchun IntEnum sanovchilari."""

from enum import IntEnum


class JobStatus(IntEnum):
    """Rekognossirovka vazifasi holatlari."""

    IDLE = 0
    READY = 1
    RUNNING = 2
    COMPLETED = 3
    CANCELLED = 4
    FAILED = 5


class SensorKind(IntEnum):
    """Sun'iy yo'ldosh va ma'lumot manbalari."""

    UNKNOWN = 0
    SENTINEL2 = 1
    SENTINEL1 = 2
    LANDSAT = 3
    SMAP = 4
    DEM = 5
    WEATHER = 6


class LayerKind(IntEnum):
    """Qatlam turlari."""

    UNKNOWN = 0
    RGB = 1
    NDVI = 2
    EVI = 3
    NDRE = 4
    NDWI = 5
    MNDWI = 6
    NDMI = 7
    NBR = 8
    NDBI = 9
    BSI = 10
    SAR_VV = 11
    SAR_VH = 12
    SAR_RVI = 13
    SAR_WATER = 14
    LST = 15
    ELEVATION = 16
    SLOPE = 17
    ASPECT = 18
    HILLSHADE = 19
    TRI = 20
    TPI = 21
    LANDCOVER = 22
    CONFIDENCE = 23
    DELTA_NDVI = 24
    DELTA_NDWI = 25
    DELTA_NDMI = 26
    DELTA_VV = 27
    DELTA_SM = 28


class WeatherSource(IntEnum):
    """Ob-havo manbalari."""

    UNKNOWN = 0
    ERA5 = 1
    GFS_ANALYSIS = 2
    GFS_FORECAST = 3
    CHIRPS = 4


class QualityFlag(IntEnum):
    """Ma'lumot sifati bayrog'i."""

    GOOD = 0
    LOW_CONFIDENCE = 1  # 30% dan kam yaroqli piksel yoki SCL nomutanosibligi
    HIGH_CLOUD = 2
