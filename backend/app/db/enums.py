"""Ma'lumotlar bazasi uchun IntEnum sanovchilari (kichik INTEGER sifatida saqlanadi)."""

from enum import IntEnum


class JobStatus(IntEnum):
    """Rekognossirovka vazifasi holatlari (bekor qilingan run'lar bazadan o'chiriladi)."""

    RUNNING = 1
    COMPLETED = 2
    FAILED = 3


class SensorKind(IntEnum):
    """Sun'iy yo'ldosh va ma'lumot manbalari."""

    UNKNOWN = 0
    SENTINEL2 = 1
    SENTINEL1 = 2
    LANDSAT = 3
    SMAP = 4
    DEM = 5
    WEATHER = 6
    DERIVED = 7  # bir nechta manbadan hosil qilingan (yer qoplami, o'zgarishlar)


SENSOR_NAMES_UZ = {
    SensorKind.UNKNOWN: "Nomaʼlum",
    SensorKind.SENTINEL2: "Sentinel-2",
    SensorKind.SENTINEL1: "Sentinel-1",
    SensorKind.LANDSAT: "Landsat 8/9",
    SensorKind.SMAP: "SMAP L4",
    SensorKind.DEM: "Copernicus DEM",
    SensorKind.WEATHER: "Ob-havo",
    SensorKind.DERIVED: "Hosila (bir nechta manba)",
}


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
    SAR_VH_MINUS_VV = 29
    DEPRESSIONS = 30
    BRIGHTNESS = 31
    EXCESS_GREEN = 32
    TEXTURE = 33
    CHROMA_GREEN = 34
    SOIL_MOISTURE_SURFACE = 35
    SOIL_MOISTURE_ROOTZONE = 36
    FALSE_COLOR = 37
    LANDSAT_NDVI = 38
    CLASS_CHANGE = 39
    DELTA_NBR = 40


class WeatherSource(IntEnum):
    """Ob-havo manbalari."""

    UNKNOWN = 0
    ERA5 = 1
    GFS_ANALYSIS = 2
    GFS_FORECAST = 3
    CHIRPS = 4


WEATHER_SOURCE_KEYS = {
    WeatherSource.ERA5: "era5",
    WeatherSource.GFS_ANALYSIS: "gfs_analysis",
    WeatherSource.GFS_FORECAST: "gfs_forecast",
    WeatherSource.CHIRPS: "chirps",
}


class QualityFlag(IntEnum):
    """Ma'lumot sifati bayrog'i."""

    GOOD = 0
    LOW_CONFIDENCE = 1  # 30% dan kam yaroqli piksel
    HIGH_CLOUD = 2  # bulut bilan niqoblangan ulush yuqori (lekin yaroqli ulush yetarli)
    NO_DATA = 3  # birorta ham yaroqli piksel yo'q


class ReportStatus(IntEnum):
    """AI hisoboti holati."""

    OK = 1
    FAILED = 2
