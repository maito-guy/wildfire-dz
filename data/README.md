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

| — | `build_static_raster.py` (repo root: `make static-raster`) | Same terrain/fuel definitions as step 4, for **every** 375 m cell of northern Algeria (`config.yaml → static_raster.bbox`, north of 34.5°N) → `out/static_375m.npz`. Needs no other step | ~25 min in one process (measured ~50 s per 1°×1°, ~30 deg²); `--shard i/4` in 4 terminals ≈ 7 min. Resumable (chunk cache in `data/cache_static_raster/`) |

Run it **on a laptop**: the sources block cloud sandboxes. `make data` runs all 5 in order. Check each script's
arguments first, since the Makefile only knows the `--export` flag of step 2.

## Outputs the rest of the repo expects (git-ignored, share through Drive)

| File | Who reads it | Schema |
|---|---|---|
| `out/train.parquet` | `model/` | see `docs/contracts.md` → Data contract |
| `out/places.parquet` | `api/impact.py` | `id, name, lat, lon` (+ optional `name_ar`); the 10,258 OSM settlements from the Algeria Fire Map export |
| `out/replay_passes.parquet` | `api/replay.py` | `holdout, t, lat, lon` (+ optional `satellite, frp`); one row per burning cell per pass, for the 2 held-out fires |
| `out/holdout_dense.parquet` | `model/villages.py` (`make evaluate`) | `train.parquet` columns + `holdout, grid_lat0, grid_lon0, grid_mlon`; every cell, not sampled |
| `out/static_375m.npz` | `core/static_raster.py` (`load()`, `lookup()`, `lookup_many()`); the feature builder #18 and the API | one grid: `lat0, lon0, mlon, cell_m, m_per_deg_lat` + float32 `(ny, nx)` layers `elev, elev_std, slope, aspect, fuel_*`; lookups return the `train.parquet` names (`aspect_sin/cos`). ~30–45 MB (estimate) |
| `out/events_replay.parquet`, `out/events_dense.parquet` | `model/crossval.py` only | same two shapes for `config.yaml → crossval.events`; the API and training never read them |

Until `places` and `replay_passes` exist, the API serves stub villages and one synthetic fire, both flagged as stub.

Credit: NASA FIRMS (VIIRS 375 m) via the Algeria Fire Map open-source export. Check the repo licence before the pitch.

## The static raster (`build_static_raster.py`, #17)

The "start a fire here" click can be anywhere, and the API cannot read DEM/WorldCover tiles live, so
`make static-raster` precomputes step 4's terrain and fuel once for the whole north. It imports
`firedata/04_terrain_fuel.py` (no copy) and treats the bbox as one big fire grid in the sense of `02_clean.py`
(corner = bbox south-west, `mlon` = 111,320·cos(centre latitude), same `floor()` snap), filled in 128-cell
chunks with a 2-cell halo. As in step 4, only an HTTP 404 tile is sea; a chunk whose read fails is skipped,
never saved, and the file is written only once every chunk is there (rerun to finish).

- **Values vs. the training table.** On a fire grid lying on the raster's cells, step 4 and the raster agree
  exactly for `elev, elev_std, slope, aspect` (checked live near Tizi Ouzou), and fuel shares agree up to
  step 4's own WorldCover sampling (1 pixel in 3, counted from each read window's corner: up to ±0.08 per cell).
  A real training fire has its own corner and `mlon`, so its cells are shifted by up to half a cell from the
  raster's: in steep terrain the same point can differ by tens of metres of elevation. For train/serve
  consistency, the feature builder (#18) should take terrain and fuel from this raster for training rows too.
- Shard: `.venv/bin/python data/build_static_raster.py --shard 0/4` (…`3/4`) in four terminals; the last one
  to finish writes the file. A small area: `--bbox W S E N --out /tmp/x.npz`.

