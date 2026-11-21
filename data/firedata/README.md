# Wildfire training data: download and clean

Seven scripts, run in order, from this folder (6 and 7 only build evaluation and API files). Everything lands in `data/` (set `FIREDATA_DIR` to put it elsewhere).
Settings (countries, years, months, thresholds) are all in `config.py`.

```
pip install -r requirements.txt
export FIRMS_MAP_KEY=your_key        # Windows: set FIRMS_MAP_KEY=your_key
python 01_download_firms.py           # ~1-1.5 h (FIRMS rate limit), resumable
python 02_clean.py --export path/to/detections.csv   # ~5-30 min
python 03_weather.py                  # resumable; max ~9,000 fires a day (free Open-Meteo limit)
python 04_terrain_fuel.py             # resumable; ~1-3 s per fire
python 05_build_table.py              # -> data/out/train.parquet
python 06_places_replay.py --export-dir path/to/export   # -> places + replay_passes (API)
python 07_holdout_dense.py            # -> holdout_dense (village scoring on the holdouts)
python 06_places_replay.py --events && python 07_holdout_dense.py --events   # -> crossval.events files
```

Get the free FIRMS key first: https://firms.modaps.eosdis.nasa.gov/api/map_key/ (arrives by email in a minute).
Steps 3 and 4 can run at the same time in two terminals. Step 5 skips fires whose weather or terrain
isn't there yet, so you can build a first table early (Algeria is fetched first) and rebuild later.

## What each step does

| Step | Source | What comes out |
|---|---|---|
| 1 | NASA FIRMS, VIIRS 375 m (S-NPP, NOAA-20, NOAA-21), June-October 2012-2026, for Algeria, Tunisia, Morocco, Spain, Portugal, Greece, Turkey | `raw_firms/*.csv`. Replaces the export's 85 empty windows automatically |
| 2 | Step 1 + the Algeria Fire Map export | Drops low-confidence, Sahara and duplicate detections, and gas flares (750 m blocks seen on 15+ days across 3+ years). Groups detections into fires, fires into satellite passes, and lists pairs of passes 20 min-16 h apart with how many new cells burned |
| 3 | Open-Meteo archive (ERA5), hourly | Per fire: temperature, humidity, VPD, wind speed/direction/gusts, rain, soil moisture, from 10 days before the fire |
| 4 | Copernicus DEM 90 m, ESA WorldCover 10 m (2021), read remotely | Per fire, on its 375 m grid: elevation, roughness, slope, aspect, and the share of tree, shrub, grass, crop, built, bare, water |
| 5 | Steps 2-4 | `train.parquet`: one row per cell within 3 km of the fire per pass pair; `label` = burning at the next pass |
| 6 | Step 2 + the export's `places.csv` | `places.parquet` and `replay_passes.parquet` for the holdouts in the repo's `config.yaml` (`--events`: `crossval.events`) |
| 7 | Steps 2-5 | Step 5's rows for every cell around the holdout fires (`--events`: `crossval.events`), for village scoring |

## Things to know before training

- **Two labels of growth.** A cell counts as new only if it is more than one cell (375 m) from anything already burning
  (`JITTER_CELLS = 1`): VIIRS pixels wobble by about a cell between passes, and that wobble looks like spread.
  On the Algeria export this leaves 311 of 9,802 short pairs with 5+ new cells; counting cells right next to
  the fire gives 1,274. Set `JITTER_CELLS = 0` in `config.py` to train on the looser label.
- **Step 4 needs a steady connection.** A tile the server says does not exist (HTTP 404) is sea; any other failed
  read is retried and the fire is skipped, never saved as "0 m, all water". Before 2026-11-21 an outage did save
  4,819 fires that way; check with: every `cache_static/*.npz` has some non-zero `elev` and `fuel_water` below 1.
- **Negatives are sampled.** Only 30% of non-burning cells are kept; use the `weight` column in training.
- **No detection does not mean no fire.** Cloud, smoke and the satellite's viewing angle hide fire. Treat label 0 as "not seen".
- **Weather after the first pass is the real weather**, not a forecast (history has no forecasts). In live use the
  forecast will be a bit worse than this.
- **Hold out whole fires**, never random rows: rows from one fire are near-copies of each other.
  Suggested holdouts: Kabylie 5-16 Aug 2021 and Jijel/Guelma 26 Aug-8 Sep 2026 (filter on `fire_id` via `fires.parquet` dates and location).
- Credit: NASA FIRMS; Open-Meteo (CC BY 4.0, free for non-commercial use); Copernicus DEM; ESA WorldCover 2021 (CC BY 4.0); Algeria Fire Map export.

## Tested here

Step 2 ran on the Algeria export (710k VIIRS detections -> 39,709 fires, 9,802 short pairs, 5,613 long pairs, 3.5 min).
Step 4 was checked on synthetic map tiles (slope, aspect, elevation and fuel shares come out exactly as built).
Step 5 was run on fake weather and terrain (209k rows from 60 fires, no missing values).
Steps 1, 3 and 4's live downloads could not be run here (no internet access to those sites), so watch the first minutes of each.
