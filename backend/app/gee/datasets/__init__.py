"""GEE kolleksiyalari va band nomlari.

Har bir ID va band nomi GEE katalogida tekshirilgan (04.10.2026, docs/DECISIONS.md, 5-qaror).
Faqat SIMPLE.md §5 dagi bandlar yuklanadi.
"""

# Sentinel-2 Harmonized Surface Reflectance (DN / 10000, uint16)
S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
S2_REFLECTANCE_BANDS = ["B2", "B3", "B4", "B5", "B8", "B8A", "B11", "B12"]
S2_QA_BANDS = ["SCL"]
S2_BANDS = S2_REFLECTANCE_BANDS + S2_QA_BANDS
S2_CLOUD_PROPERTY = "CLOUDY_PIXEL_PERCENTAGE"
S2_PLATFORM_PROPERTY = "SPACECRAFT_NAME"

# Cloud Score+ (Sentinel-2 bilan system:index bo'yicha bog'lanadi)
S2_CLOUD_SCORE_PLUS_COLLECTION = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
CLOUD_SCORE_BAND = "cs_cdf"

# Sentinel-1 GRD, IW rejimi (allaqachon dB da)
S1_COLLECTION = "COPERNICUS/S1_GRD"
S1_BANDS = ["VV", "VH"]
S1_INSTRUMENT_MODE = "IW"
S1_PASS_PROPERTY = "orbitProperties_pass"

# Landsat 8 va 9 Collection 2 Level 2
LANDSAT_COLLECTIONS = {
    "LC08": "LANDSAT/LC08/C02/T1_L2",
    "LC09": "LANDSAT/LC09/C02/T1_L2",
}
LANDSAT_SR_BANDS = ["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"]
LANDSAT_THERMAL_BANDS = ["ST_B10"]
LANDSAT_QA_BANDS = ["QA_PIXEL"]
LANDSAT_BANDS = LANDSAT_SR_BANDS + LANDSAT_THERMAL_BANDS + LANDSAT_QA_BANDS
LANDSAT_CLOUD_PROPERTY = "CLOUD_COVER"

# SMAP L4 tuproq namligi (3 soatlik, eng yangi versiya: 008)
SMAP_COLLECTION = "NASA/SMAP/SPL4SMGP/008"
SMAP_BANDS = ["sm_surface", "sm_rootzone"]

# Copernicus DEM GLO-30 (GLO30 eskirgan, o'rniga GLO30_2024_1)
DEM_COLLECTION = "COPERNICUS/DEM/GLO30_2024_1"
DEM_BAND = "DEM"

# Ob-havo
ERA5_LAND_HOURLY = "ECMWF/ERA5_LAND/HOURLY"
ERA5_BANDS = [
    "temperature_2m",
    "dewpoint_temperature_2m",
    "total_precipitation_hourly",
    "u_component_of_wind_10m",
    "v_component_of_wind_10m",
    "volumetric_soil_water_layer_1",
]

GFS_0P25 = "NOAA/GFS0P25"
GFS_BANDS = [
    "temperature_2m_above_ground",
    "dew_point_temperature_2m_above_ground",
    "relative_humidity_2m_above_ground",
    "total_precipitation_surface",
    "u_component_of_wind_10m_above_ground",
    "v_component_of_wind_10m_above_ground",
    "total_cloud_cover_entire_atmosphere",
]
GFS_PRECIP_BAND = "total_precipitation_surface"
GFS_BUCKET_HOURS = 6  # yog'in ((F - 1) % 6) + 1 soatlik bo'lakda to'planadi

# CHIRPS v3 kunlik (yaqin real vaqt, IMERG asosida). "V3/DAILY" degan ID katalogda yo'q.
CHIRPS_DAILY = "UCSB-CHC/CHIRPS/V3/DAILY_SAT"
CHIRPS_BAND = "precipitation"

# Reanaliz/prognoz to'rlarining taxminiy o'lchami — kichik AOI uchun reduceRegion masshtabi
ERA5_SCALE_M = 11132
GFS_SCALE_M = 27830
CHIRPS_SCALE_M = 5566
SMAP_SCALE_M = 11000
WEATHER_REDUCE_SCALE_M = 1000  # piksel markazi AOI ichiga tushmasa ham qiymat olish uchun
