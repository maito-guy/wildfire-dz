"""Shared settings for the wildfire data pipeline. Edit here, not in the scripts."""
import os
from pathlib import Path

ROOT = Path(os.environ.get("FIREDATA_DIR", Path(__file__).parent / "data"))
RAW_FIRMS = ROOT / "raw_firms"        # one CSV per country/source/10-day window
CACHE_WEATHER = ROOT / "cache_weather"  # one JSON per fire
CACHE_STATIC = ROOT / "cache_static"    # one .npz per fire (elevation, slope, fuel)
OUT = ROOT / "out"                      # clean tables: detections, fires, pairs, train
for p in (RAW_FIRMS, CACHE_WEATHER, CACHE_STATIC, OUT):
    p.mkdir(parents=True, exist_ok=True)

# Free key: https://firms.modaps.eosdis.nasa.gov/api/map_key/  (set FIRMS_MAP_KEY in your shell)
FIRMS_MAP_KEY = os.environ.get("FIRMS_MAP_KEY", "")

# Algeria + countries with a similar (Mediterranean) fire climate. ISO-3 codes.
COUNTRIES = ["DZA", "TUN", "MAR", "ESP", "PRT", "GRC", "TUR"]
YEARS = range(2012, 2027)        # VIIRS S-NPP starts Jan 2012
MONTHS = (6, 7, 8, 9, 10)        # fire season only; widen if you want more data
SOURCE_PREFIXES = ("VIIRS_SNPP", "VIIRS_NOAA20", "VIIRS_NOAA21")  # 375 m sensors only

# Only northern Algeria (Sahara detections are mostly industrial). Other countries: no cut.
DZA_MIN_LAT = 34.5

# 375 m grid
CELL_M = 375.0
M_PER_DEG_LAT = 110_574.0

# Gas flares / industrial hotspots: a cell seen on this many distinct days across this many years
FLARE_MIN_DAYS, FLARE_MIN_YEARS = 15, 3

# Fire clustering: detections join the same fire if within this many cells and hours
CLUSTER_RADIUS_CELLS, CLUSTER_GAP_HOURS = 3, 48

# Pass pairs used for training (minutes between passes)
SHORT_PAIR = (20, 120)     # teaches 1-hour spread
LONG_PAIR = (120, 16 * 60) # teaches longer runs

# A "new" burning cell must be more than this many cells from anything burned before
# (VIIRS pixels grow off-nadir and wobble by ~1 cell; this stops wobble counting as spread)
JITTER_CELLS = 1

# Training rows: candidate cells within this many cells (x 375 m) of the current fire
CANDIDATE_RADIUS_CELLS = 8   # 3 km
NEG_KEEP = 0.3               # keep this share of negative cells (weight column corrects for it)
GRID_MARGIN_CELLS = 16       # margin around each fire's bounding box for terrain/fuel grids

# Remote rasters (public, no key)
DEM_URL = ("https://copernicus-dem-90m.s3.eu-central-1.amazonaws.com/"
           "Copernicus_DSM_COG_30_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM/"
           "Copernicus_DSM_COG_30_{ns}{lat:02d}_00_{ew}{lon:03d}_00_DEM.tif")
WORLDCOVER_URL = ("https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/"
                  "ESA_WorldCover_10m_2021_v200_{ns}{lat:02d}{ew}{lon:03d}_Map.tif")
# WorldCover classes kept as fuel fractions
FUEL_CLASSES = {10: "tree", 20: "shrub", 30: "grass", 40: "crop", 50: "built", 60: "bare", 80: "water"}

OPEN_METEO_URL = "https://archive-api.open-meteo.com/v1/archive"
WEATHER_VARS = ["temperature_2m", "relative_humidity_2m", "vapour_pressure_deficit",
                "wind_speed_10m", "wind_direction_10m", "wind_gusts_10m",
                "precipitation", "soil_moisture_0_to_7cm"]
WEATHER_LOOKBACK_DAYS = 10   # to compute "hours since rain"
