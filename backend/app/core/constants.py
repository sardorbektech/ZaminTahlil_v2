"""Tizim konstantalari va tahlil chegaralari.

Barcha ostonaviy qiymatlar (thresholds) va standart sozlamalar shu yerda jamlangan.
Funksiyalar ichida raqamlar qattiq yozilmaydi — shu moduldan olinadi.
"""

# ---------------------------------------------------------------------------
# Standart sozlamalar qiymatlari (SIMPLE.md §11)
# ---------------------------------------------------------------------------
DEFAULT_LOOKBACK_DAYS = 10
DEFAULT_WEATHER_PAST_DAYS = 5
DEFAULT_WEATHER_FORECAST_DAYS = 5
DEFAULT_MAX_SCENE_CLOUD_PCT = 40.0
DEFAULT_CLOUD_SCORE_THRESHOLD = 0.60
DEFAULT_S1_ORBIT_PASS = "BOTH"
DEFAULT_ANALYSIS_RESOLUTION_M = 10.0
DEFAULT_MAX_AOI_KM2 = 100.0
DEFAULT_GEE_REQUEST_TIMEOUT_S = 60
DEFAULT_GEE_MAX_RETRIES = 3
DEFAULT_GEE_MAX_CONCURRENCY = 6
DEFAULT_AI_PROVIDER = "openrouter"
DEFAULT_AI_MODEL = "openrouter/free"
DEFAULT_AI_HISTORY_SIZE = 10

# Sozlamalar uchun ruxsat etilgan oraliqlar
LOOKBACK_DAYS_RANGE = (1, 60)
WEATHER_DAYS_RANGE = (1, 10)
CLOUD_PCT_RANGE = (0.0, 100.0)
CLOUD_SCORE_RANGE = (0.0, 1.0)
RESOLUTION_M_RANGE = (10.0, 100.0)
MAX_AOI_KM2_RANGE = (0.01, 100.0)
GEE_TIMEOUT_RANGE = (5, 600)
GEE_RETRIES_RANGE = (0, 10)
GEE_CONCURRENCY_RANGE = (1, 20)
AI_HISTORY_RANGE = (1, 50)
S1_ORBIT_PASS_VALUES = ("BOTH", "ASCENDING", "DESCENDING")
AI_PROVIDERS = ("openrouter", "openai", "ollama")

# ---------------------------------------------------------------------------
# Quvur (pipeline) cheklovlari
# ---------------------------------------------------------------------------
RETENTION_MAX_AGE_S = 24 * 3600  # 24 soatdan eski run'lar o'chiriladi
RETENTION_INTERVAL_S = 600  # har 10 daqiqada tozalash
USAGE_LOG_RETENTION_DAYS = 30  # API jurnallari 30 kun saqlanadi
CANCEL_WAIT_S = 2.0  # bekor qilishda vazifa tugashini kutish chegarasi
MAX_GRID_PIXELS = 16_000_000  # bitta to'rning maksimal piksellari (bbox bo'yicha)
TILE_SIZE_PX = 512  # computePixels bo'lagi (GEE 48 MB chegarasidan ancha past)
MIN_TILE_SIZE_PX = 64  # "User memory limit exceeded" da bo'lish uchun pastki chegara
GEE_BACKOFF_BASE_S = 1.0  # qayta urinish kutishi: base * 2^n + jitter
GEE_BACKOFF_MAX_S = 20.0
CROSS_CHECK_MAX_DAYS = 3.0  # S2 va Landsat NDVI taqqoslash oynasi
WEB_MERCATOR_HALF = 20037508.342789244  # EPSG:3857 yarim ekvator uzunligi (m)
EARTH_RADIUS_M = 6378137.0

# Yuklab olishda niqoblangan piksellar uchun belgi (sentinel) qiymatlar
NODATA_UINT16 = 0
NODATA_FLOAT = -9999.0

# ---------------------------------------------------------------------------
# Masshtablash koeffitsiyentlari (GEE katalogi bo'yicha tekshirilgan)
# ---------------------------------------------------------------------------
S2_SR_SCALE = 1.0 / 10000.0  # Sentinel-2 SR: DN / 10000
CLOUD_SCORE_UINT_SCALE = 10000.0  # cs_cdf uint16 sifatida yuklanadi: qiymat * 10000
LANDSAT_SR_MULT = 0.0000275  # Landsat SR: DN * 0.0000275 - 0.2
LANDSAT_SR_ADD = -0.2
LANDSAT_ST_MULT = 0.00341802  # Landsat ST_B10: DN * 0.00341802 + 149.0 (Kelvin)
LANDSAT_ST_ADD = 149.0
KELVIN_OFFSET = 273.15
ERA5_PRECIP_M_TO_MM = 1000.0  # ERA5-Land yog'in metrda beriladi

# Sentinel-2 SCL sinflari
SCL_CLOUD_SHADOW = 3
SCL_VEGETATION = 4
SCL_NOT_VEGETATED = 5
SCL_WATER = 6
SCL_CLOUD_CLASSES = (3, 8, 9, 10)  # soya, o'rtacha/yuqori bulut, sirrus
SCL_INVALID_CLASSES = (0, 1)  # no data, saturated

# Landsat QA_PIXEL bitlari: 0 fill, 1 dilated cloud, 2 cirrus, 3 cloud, 4 cloud shadow
LANDSAT_QA_MASK_BITS = (0, 1, 2, 3, 4)

# ---------------------------------------------------------------------------
# Tahlil va indeks chegaralari
# ---------------------------------------------------------------------------
WATER_VV_MAX_DB = -15.0  # SAR da suv uchun VV ning maksimal qiymati (dB)
LEE_WINDOW = 5  # Lee filtr darchasi
LEE_ENL = 4.4  # Sentinel-1 IW GRD ekvivalent ko'rinishlar soni (ENL)
TEXTURE_WINDOW = 5
TPI_WINDOW = 5
DEPRESSION_TPI_MAX = -1.0  # m
DEPRESSION_SLOPE_MAX_DEG = 3.0
HILLSHADE_AZIMUTH_DEG = 315.0
HILLSHADE_ALTITUDE_DEG = 45.0
LOW_VALID_PIXEL_PCT_THRESHOLD = 30.0  # Shu qiymatdan past bo'lsa "past ishonchlilik" belgisi
HIGH_CLOUD_PCT_THRESHOLD = 60.0  # bulut bilan niqoblangan ulush shundan katta bo'lsa

# Yer qoplami qoidalari (SIMPLE.md §7.4)
LC_WATER_MNDWI_MIN = 0.1
LC_WATER_NDWI_MIN = 0.2
LC_WATER_VV_MAX_DB = WATER_VV_MAX_DB
LC_WATER_VH_MAX_DB = -22.0
LC_SWAMP_NDWI_MIN = -0.1
LC_SWAMP_NDMI_MIN = 0.0
LC_SWAMP_NDVI_RANGE = (0.1, 0.5)
LC_SWAMP_VV_MAX_DB = -12.0
LC_SWAMP_SM_MIN = 0.30  # m3/m3 (SMAP)
LC_SWAMP_MIN_EVIDENCE = 3  # 5 ta dalildan kamida nechtasi
LC_FOREST_NDVI_MIN = 0.6
LC_FOREST_TEXTURE_MIN = 0.015  # yorqinlik std (aks ettirish birligida)
LC_FOREST_VH_MIN_DB = -17.0
LC_CROP_NDVI_RANGE = (0.3, 0.6)
LC_CROP_TEXTURE_MAX = 0.03
LC_SPARSE_NDVI_RANGE = (0.15, 0.3)
LC_BARE_BSI_MIN = 0.0
LC_BARE_NDVI_MAX = 0.15
LC_BUILT_NDBI_MIN = 0.0
LC_BUILT_NDVI_MAX = 0.2
LC_BUILT_VV_MIN_DB = -8.0
LC_BURNT_NBR_MAX = 0.1
LC_BURNT_DNBR_MAX = -0.27  # NBR pasayishi (USGS past darajali kuyish chegarasi)
LC_ROAD_MIN_PIXELS = 10
LC_ROAD_MIN_ELONGATION = 4.0  # uzunlik / kenglik (asosiy o'qlar nisbati)
LC_ROAD_MAX_FILL_RATIO = 0.35  # komponent / to'ldirilgan qobiq maydoni
LC_BRIDGE_WATER_DILATION_PX = 1

# Ishonchlilik qiymatlari
LC_CONF_BASE = {
    1: 0.90,  # suv
    2: 0.55,  # botqoqlik
    3: 0.85,  # daraxtzor
    4: 0.75,  # ekin
    5: 0.70,  # siyrak o'simlik
    6: 0.75,  # ochiq tuproq
    7: 0.70,  # imorat
    8: 0.50,  # yo'l (ehtimoliy)
    9: 0.40,  # ko'prik (ehtimoliy)
    10: 0.60,  # kuygan hudud
}
LC_CONF_SCL_PENALTY = 0.25  # SCL bilan ziddiyatda pasaytirish
LC_CONF_MIN = 0.05

# O'zgarishlar
CHANGE_TRANSITION_MIN_PCT = 0.1  # shu foizdan kam o'tishlar ko'rsatilmaydi

# ---------------------------------------------------------------------------
# Ob-havo ta'siri qoidalari
# ---------------------------------------------------------------------------
WX_HEAVY_RAIN_PAST_MM = 10.0
WX_DRY_PAST_MM = 1.0
WX_WATERLOG_FORECAST_MM = 15.0
WX_FROST_C = 0.0
WX_HEAT_C = 38.0
WX_STRONG_WIND_MS = 12.0
WX_DAILY_HEAVY_RAIN_MM = 20.0
WX_SM_CHANGE_SIGNIFICANT = 0.02  # m3/m3
WX_VV_CHANGE_SIGNIFICANT_DB = 1.0
WX_NDVI_CHANGE_SIGNIFICANT = 0.05
WX_LST_AIR_DIFF_SIGNIFICANT_C = 8.0

# ---------------------------------------------------------------------------
# Yer qoplami (Land Cover) sinflari kodlari
# ---------------------------------------------------------------------------
CLASS_UNKNOWN = 0
CLASS_WATER = 1
CLASS_SWAMP = 2
CLASS_FOREST = 3
CLASS_CROPLAND = 4
CLASS_SPARSE_VEG = 5
CLASS_BARE_SOIL = 6
CLASS_BUILTUP = 7
CLASS_ROAD = 8
CLASS_BRIDGE = 9
CLASS_BURNT = 10

CLASS_LABELS_UZ = {
    CLASS_UNKNOWN: "Nomaʼlum / bulut",
    CLASS_WATER: "Suv",
    CLASS_SWAMP: "Botqoqlik",
    CLASS_FOREST: "Daraxtzor",
    CLASS_CROPLAND: "Ekin / dala",
    CLASS_SPARSE_VEG: "Siyrak oʻsimlik",
    CLASS_BARE_SOIL: "Ochiq tuproq",
    CLASS_BUILTUP: "Imorat",
    CLASS_ROAD: "Yoʻl (ehtimoliy)",
    CLASS_BRIDGE: "Koʻprik (ehtimoliy)",
    CLASS_BURNT: "Kuygan hudud",
}

CLASS_COLORS = {
    CLASS_UNKNOWN: "#000000",
    CLASS_WATER: "#1f78ff",
    CLASS_SWAMP: "#2e8b57",
    CLASS_FOREST: "#006400",
    CLASS_CROPLAND: "#9be22d",
    CLASS_SPARSE_VEG: "#d8c27a",
    CLASS_BARE_SOIL: "#a0522d",
    CLASS_BUILTUP: "#ff4500",
    CLASS_ROAD: "#bdbdbd",
    CLASS_BRIDGE: "#ffd700",
    CLASS_BURNT: "#5a0000",
}

NO_DATA_UZ = "maʼlumot yoʻq"
LOW_CONFIDENCE_UZ = "past ishonchlilik"
