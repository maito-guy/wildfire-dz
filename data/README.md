# data/ — the firedata pipeline, kept as is

Copy the 5 scripts from `firedata.zip` into this folder **unchanged** (plus its own requirements file if it has one).
Lint skips this folder on purpose. Changes go in small PRs from the `data` branch only.

| Step | Script | What it does | Time / limits |
|---|---|---|---|
| 1 | `01_download_firms.py` | VIIRS 375 m, June–Oct 2012–2026, for DZA TUN MAR ESP PRT GRC TUR (FIRMS country API) | ~1–1.5 h; 5,000 transactions / 10 min; needs `FIRMS_MAP_KEY` in `.env` |
| 2 | `02_clean.py --export detections.csv` | confidence filter, Sahara cut, duplicates, gas flares; fires → passes → pairs | — |
| 3 | `03_weather.py` | Open-Meteo ERA5 hourly per fire, **Algeria first** | 10,000 calls / day (free) |
| 4 | `04_terrain_fuel.py` | Copernicus DEM 90 m + ESA WorldCover 10 m onto each fire's 375 m grid (remote COG reads) | — |
| 5 | `05_build_table.py` | → `data/out/train.parquet` | — |
| 6 | `06_places_replay.py --export-dir <export>` | → `places.parquet`, `replay_passes.parquet` (API); `--events`: `events_replay.parquet` | seconds |
| 7 | `07_holdout_dense.py` | every cell around the holdout fires → `holdout_dense.parquet`; `--events`: `events_dense.parquet` | ~1 min |

**Dashboard data only (no downloads, ~10 s):** put the export in `data/algeria-fire-map-data/` and run
`make import-export` (`EXPORT_DIR=...` for another folder). `firedata/import_export.py` writes `out/detections.parquet`
(VIIRS, all months), runs step 6, builds `out/history_grid.parquet`, and turns the export's `cell_risk.csv` into
`model/artifacts/risk_today.parquet` until `model.risk` (#27) writes it. A later step 2 run overwrites
`out/detections.parquet` with the same columns (fire season only).

Run it **on a laptop**: the sources block cloud sandboxes. `make data` runs all 5 in order. Check each script's
arguments first, since the Makefile only knows the `--export` flag of step 2.

## Outputs the rest of the repo expects (git-ignored, share through Drive)

| File | Who reads it | Schema |
|---|---|---|
| `out/train.parquet` | `model/` | see `docs/contracts.md` → Data contract |
| `out/places.parquet` | `api/impact.py` | `id, name, lat, lon` (+ optional `name_ar`); the 10,258 OSM settlements from the Algeria Fire Map export |
| `out/replay_passes.parquet` | `api/replay.py` | `holdout, t, lat, lon` (+ optional `satellite, frp`); one row per burning cell per pass, for the 2 held-out fires |
| `out/detections.parquet`, `out/history_grid.parquet` | `api/detections.py` | see `docs/contracts.md` (v0.5) |
| `out/holdout_dense.parquet` | `model/villages.py` (`make evaluate`) | `train.parquet` columns + `holdout, grid_lat0, grid_lon0, grid_mlon`; every cell, not sampled |
| `out/events_replay.parquet`, `out/events_dense.parquet` | `model/crossval.py` only | same two shapes for `config.yaml → crossval.events`; the API and training never read them |

Until `places` and `replay_passes` exist, the API serves stub villages and one synthetic fire, both flagged as stub.

Credit: NASA FIRMS (VIIRS 375 m) via the Algeria Fire Map open-source export. Check the repo licence before the pitch.
