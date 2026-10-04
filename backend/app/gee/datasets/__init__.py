"""GEE kolleksiyalari va band nomlari konstantalari."""

# Sentinel-2 Harmonized Surface Reflectance
S2_COLLECTION = "COPERNICUS/S2_SR_HARMONIZED"
S2_CLOUD_SCORE_PLUS_COLLECTION = "GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED"
S2_BANDS = ["B2", "B3", "B4", "B5", "B8", "B8A", "B11", "B12", "SCL"]

# Sentinel-1 GRD IW Mode
S1_COLLECTION = "COPERNICUS/S1_GRD"
S1_BANDS = ["VV", "VH"]

# Landsat 8 va 9 Level 2
LANDSAT_8_COLLECTION = "LANDSAT/LC08/C02/T1_L2"
LANDSAT_9_COLLECTION = "LANDSAT/LC09/C02/T1_L2"
LANDSAT_SR_BANDS = ["SR_B2", "SR_B3", "SR_B4", "SR_B5", "SR_B6", "SR_B7"]
LANDSAT_THERMAL_BANDS = ["ST_B10"]
LANDSAT_QA_BANDS = ["QA_PIXEL"]

# SMAP L4 Soil Moisture
SMAP_COLLECTION = "NASA/SMAP/SPL4SMGP/007"
SMAP_BANDS = ["sm_surface", "sm_rootzone"]

# Copernicus DEM GLO-30
DEM_COLLECTION = "COPERNICUS/DEM/GLO30"
DEM_BAND = "DEM"

# Ob-havo kolleksiyalari
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
    "relative_humidity_2m_above_ground",
    "total_precipitation_surface",
    "u_component_of_wind_10m_above_ground",
    "v_component_of_wind_10m_above_ground",
    "total_cloud_cover_entire_atmosphere",
]

CHIRPS_DAILY = "UCSB-CHC/CHIRPS/V3/DAILY"
CHIRPS_BAND = "precipitation"
