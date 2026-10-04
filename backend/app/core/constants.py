"""Tizim konstantalari va tahlil chegaralari.

Barcha ostonaviy qiymatlar (thresholds) va standart sozlamalar shu yerda jamlangan.
"""

# Standart sozlamalar qiymatlari
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

# Tahlil va indeks chegaralari
WATER_VV_MAX_DB = -15.0  # SAR da suv uchun VV ning maksimal qiymati (dB)
LOW_VALID_PIXEL_PCT_THRESHOLD = 30.0  # Shu qiymatdan past bo'lsa "past ishonchlilik" belgisi

# Yer qoplami (Land Cover) sinflari kodlari
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

# RGB ranglari (vizualizatsiya uchun HEX va RGB)
CLASS_COLORS = {
    CLASS_UNKNOWN: "#000000",
    CLASS_WATER: "#0077be",
    CLASS_SWAMP: "#2e8b57",
    CLASS_FOREST: "#006400",
    CLASS_CROPLAND: "#7cfc00",
    CLASS_SPARSE_VEG: "#d2b48c",
    CLASS_BARE_SOIL: "#a0522d",
    CLASS_BUILTUP: "#ff4500",
    CLASS_ROAD: "#808080",
    CLASS_BRIDGE: "#ffd700",
    CLASS_BURNT: "#8b0000",
}
