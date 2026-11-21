"""Turn a fire mask into 1 h / 2 h zones and per-cell arrival times with model A, B or C (#20).

Model C (LightGBM, `model/train.py`) is read from the files `python -m model.export` publishes in
paths.artifacts: `api_manifest.json` -> model_c {tag, features, files, prob_threshold}, `features.json`
(the matrix columns) and the booster files. The arrival threshold is thresholds.json C_<tag>.prob_time
(the one model/evaluate.py tunes for minutes-to-arrival), else the manifest's prob_threshold.

C on a mask: the mask becomes one satellite pass (frp = api.model_c.mask_frp_mw per point); hourly weather
comes from Open-Meteo with the request's wind written over it, so B and C see the same wind; terrain and fuel
come from the static raster; `core.features.rows_from_detections` builds the rows, exactly as for training.
C's minutes-to-arrival (first g in model.villages.C_GAPS over the threshold, as villages.c_minutes) replace
B's arrival on the cells C has (features.candidate_radius_cells around the fire); B keeps the rest of the grid,
as in the village scoring.

Fail-safe: any C error, missing file or a run longer than api.predict_timeout_s -> B, with fallback_reason.
Never nothing.
"""
from __future__ import annotations

import asyncio
import concurrent.futures as cf
import datetime as dt
import json
import logging
import time as _time
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd
import shapely
from scipy.spatial import cKDTree
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

from api import weather
from core import features, geo, static_raster
from core.config import load_config, repo_path
from model import baselines

log = logging.getLogger(__name__)

HORIZONS = (60, 120)
_pool = cf.ThreadPoolExecutor(max_workers=2, thread_name_prefix="model_c")
_wx_cache: dict[tuple, tuple[float, pd.DataFrame]] = {}   # (lat, lon, start, end) -> (expires monotonic, hourly)


class ModelCUnavailable(RuntimeError):
    """C cannot run; the message goes into fallback_reason."""


@lru_cache(maxsize=8)
def _read_json(path: str, mtime: float) -> dict:          # mtime: a re-exported file is re-read
    return json.loads(Path(path).read_text())


def _json(p: Path) -> dict:
    return _read_json(str(p), p.stat().st_mtime) if p.exists() else {}


def _artifacts(cfg: dict | None = None) -> Path:
    return repo_path((cfg or load_config())["paths"]["artifacts"])


def manifest(cfg: dict | None = None) -> dict:
    return _json(_artifacts(cfg) / "api_manifest.json")


def rate_for(model: str, cfg: dict) -> float:
    m = manifest(cfg).get("rate_m_per_min", {})
    key = "baseline_a" if model == "A" else "baseline_b"
    return float(m.get(model, cfg["model"][key]["rate_m_per_min"]))


def mask_points(burning, polygon, cfg) -> tuple[np.ndarray, np.ndarray]:
    if burning:
        return np.array([p.lat for p in burning]), np.array([p.lon for p in burning])
    if polygon:
        geom = shape(polygon)
        lon0, lat0 = geom.centroid.x, geom.centroid.y
        minx, miny, maxx, maxy = geom.bounds
        x0, y0 = geo.to_xy(miny, minx, lat0, lon0)
        x1, y1 = geo.to_xy(maxy, maxx, lat0, lon0)
        c = cfg["grid"]["cell_m"]
        gx, gy = np.meshgrid(np.arange(x0, x1 + c, c), np.arange(y0, y1 + c, c))
        lat, lon = geo.to_latlon(gx.ravel(), gy.ravel(), lat0, lon0)
        inside = shapely.contains_xy(geom, lon, lat)
        if inside.any():
            return lat[inside], lon[inside]
        return np.array([lat0]), np.array([lon0])
    raise ValueError("send `burning` points or a `polygon`")


# ---------------------------------------------------------------- model C

@dataclass(frozen=True)
class LoadedC:
    model: object             # model.ensemble.ModelC (mean of the seed boosters)
    tag: str
    threshold: float          # P(burning within g) at or above this = "reached by g"


@lru_cache(maxsize=2)
def _load_c(art: str, tag: str, feats: str, files: tuple[str, ...], thr: float, stamp: tuple) -> LoadedC:
    import lightgbm as lgb

    from model.ensemble import ModelC

    meta = json.loads((Path(art) / feats).read_text())
    return LoadedC(ModelC([lgb.Booster(model_file=str(Path(art) / f)) for f in files], meta), tag, thr)


def load_c(cfg: dict | None = None) -> LoadedC:
    """Model C from the exported artifacts (cached until one of its files changes). Raises ModelCUnavailable."""
    cfg = cfg or load_config()
    art = _artifacts(cfg)
    entry = manifest(cfg).get("model_c")
    if not entry:
        raise ModelCUnavailable("model C not exported (api_manifest.json has no model_c)")
    tag = str(entry.get("tag", ""))
    feats = entry.get("features", "features.json")
    if not (art / feats).exists():
        raise ModelCUnavailable(f"model C file missing: {feats}")
    files = entry.get("files") or _json(art / feats).get("files") or ["model_c.txt"]
    missing = [f for f in files if not (art / f).exists()]
    if missing:
        raise ModelCUnavailable(f"model C file missing: {', '.join(missing)}")
    th = _json(art / "thresholds.json").get(f"C_{tag}", {})
    thr = th.get("prob_time", th.get("prob", entry.get("prob_threshold")))
    if thr is None:
        raise ModelCUnavailable(f"no threshold for model C_{tag}")
    stamp = tuple((art / f).stat().st_mtime for f in [feats, *files])
    try:
        return _load_c(str(art), tag, feats, tuple(files), float(thr), stamp)
    except Exception as e:  # noqa: BLE001 - a broken file is a fallback, not a crash
        raise ModelCUnavailable(f"model C failed to load ({type(e).__name__}: {e})") from e


def model_c_status(cfg: dict | None = None) -> tuple[bool, str | None]:
    """(True, None) when C's artifacts load, else (False, why). For /health."""
    try:
        load_c(cfg)
        return True, None
    except ModelCUnavailable as e:
        return False, str(e)


@lru_cache(maxsize=2)
def _raster(path: str, mtime: float) -> static_raster.StaticRaster:
    return static_raster.load(path)


def load_raster(cfg: dict) -> static_raster.StaticRaster:
    p = repo_path(cfg["paths"]["static_raster"])
    if not p.exists():
        raise ModelCUnavailable(f"static raster missing ({cfg['paths']['static_raster']}, `make static-raster`)")
    return _raster(str(p), p.stat().st_mtime)


async def _fetch_hourly(lat: float, lon: float, start: dt.date, end: dt.date, cfg: dict) -> pd.DataFrame:
    fc = cfg["forecast"]
    recent = start >= (dt.datetime.now(dt.UTC) - dt.timedelta(days=fc["past_days"])).date()
    url = fc["forecast_url"] if recent else fc["archive_url"]
    params = {"latitude": lat, "longitude": lon, "hourly": ",".join(features.HOURLY), "wind_speed_unit": "kmh",
              "timezone": "UTC", "start_date": start.isoformat(), "end_date": end.isoformat()}
    async with weather._make_client(fc["timeout_s"]) as c:      # the tests' offline client covers this too
        r = await c.get(url, params=params, timeout=fc["timeout_s"])
    r.raise_for_status()
    h = pd.DataFrame(r.json()["hourly"])
    return h.astype({k: float for k in features.HOURLY if k in h})


def hourly_weather(lat: float, lon: float, t: pd.Timestamp, cfg: dict) -> pd.DataFrame:
    """Open-Meteo hourly weather (core.features.HOURLY) from features.weather_lookback_days before t to the day
    after it: forecast API within forecast.past_days, else ERA5. Cached forecast.cache_min minutes; any failure
    raises ModelCUnavailable."""
    start = (t - pd.Timedelta(days=int(cfg["features"]["weather_lookback_days"]))).date()
    end = (t + pd.Timedelta(hours=3)).date()
    key = (round(lat, 2), round(lon, 2), start, end)
    hit = _wx_cache.get(key)
    if hit and hit[0] > _time.monotonic():
        return hit[1]
    try:
        h = asyncio.run(_fetch_hourly(key[0], key[1], start, end, cfg))
    except Exception as e:  # noqa: BLE001
        raise ModelCUnavailable(f"no weather for model C ({type(e).__name__}: {e})") from e
    _wx_cache[key] = (_time.monotonic() + cfg["forecast"]["cache_min"] * 60, h)
    return h


def c_arrival(c: LoadedC, lat, lon, t, wind_kmh: float, wind_from: float, cfg: dict,
              hourly: pd.DataFrame, raster: static_raster.StaticRaster) -> pd.DataFrame:
    """C's minutes-to-arrival per candidate cell: DataFrame(lat, lon, arrival). The mask is one pass at t;
    the request's wind is written over the hourly wind so B and C see the same one."""
    from model.villages import c_minutes

    t = pd.Timestamp(t)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    det = pd.DataFrame({"t": t, "sat": "mask", "lat": np.asarray(lat, float), "lon": np.asarray(lon, float),
                        "frp": float(cfg["api"]["model_c"]["mask_frp_mw"])})
    wx = hourly.assign(wind_speed_10m=float(wind_kmh), wind_direction_10m=float(wind_from))
    try:
        rows, _ = features.rows_from_detections(det, t, wx, raster, cfg)
    except ValueError as e:
        raise ModelCUnavailable(f"model C has no rows ({e})") from e
    cols = cfg["columns"]
    need = [f for f in c.model.raw if f not in rows and f not in (cols["gap_min"], cols["kind"])]
    if need:
        raise ModelCUnavailable(f"model C needs features the API does not build: {need}")
    minutes = c_minutes(rows, c.model, c.threshold, cfg)
    return pd.DataFrame({"lat": rows["lat"].to_numpy(), "lon": rows["lon"].to_numpy(), "arrival": minutes})


def merge_c(grid: dict, cells: pd.DataFrame) -> dict:
    """B's grid with C's arrival on every grid cell whose centre is within 0.75 cell of one of C's cells.
    Burning cells (B arrival 0) stay 0; cells C does not cover keep B's arrival."""
    if cells.empty:
        return grid
    cx, cy = geo.to_xy(cells["lat"].to_numpy(), cells["lon"].to_numpy(), grid["lat0"], grid["lon0"])
    d, j = cKDTree(np.c_[cx, cy]).query(np.c_[grid["x"], grid["y"]], distance_upper_bound=0.75 * grid["cell_m"])
    hit = np.isfinite(d) & (grid["arrival"] > 0)
    arrival = grid["arrival"].copy()
    arrival[hit] = cells["arrival"].to_numpy()[j[hit]]
    return {**grid, "arrival": arrival}


def _run_c(lat, lon, t, wind_kmh, wind_from, cfg) -> pd.DataFrame:
    c = load_c(cfg)
    raster = load_raster(cfg)
    hourly = hourly_weather(float(np.mean(lat)), float(np.mean(lon)), pd.Timestamp(t), cfg)
    return c_arrival(c, lat, lon, t, wind_kmh, wind_from, cfg, hourly, raster)


def run_model(model: str, lat, lon, wind_kmh, wind_from, cfg, time=None) -> tuple[str, str | None, dict]:
    """Returns (model_used, fallback_reason, grid). `time` = the mask's satellite pass (default now).
    auto = C when the manifest exports it, else B (no reason). C runs in a worker thread for at most
    api.predict_timeout_s; any error or timeout gives B and the reason."""
    base = "A" if model == "A" else "B"
    grid = baselines.arrival_grid(lat, lon, base, rate_for(base, cfg), wind_kmh, wind_from, cfg)
    if not (model == "C" or (model == "auto" and manifest(cfg).get("model_c"))):
        return base, None, grid
    timeout = float(cfg["api"]["predict_timeout_s"])
    fut = _pool.submit(_run_c, lat, lon, time or dt.datetime.now(dt.UTC), wind_kmh, wind_from, cfg)
    try:
        return "C", None, merge_c(grid, fut.result(timeout=timeout))
    except cf.TimeoutError:
        fut.cancel()
        reason = f"model C took longer than {timeout:g} s"
    except ModelCUnavailable as e:
        reason = str(e)
    except Exception as e:  # noqa: BLE001 - never answer nothing
        log.exception("model C failed")
        reason = f"model C failed ({type(e).__name__}: {e})"
    reason += "; fail-safe to B"
    log.warning("predict: %s", reason)
    return "B", reason, grid


def zones_geojson(grid: dict) -> dict:
    half = grid["cell_m"] / 2
    feats = []
    for h in HORIZONS:
        sel = grid["arrival"] <= h
        boxes = [box(x - half, y - half, x + half, y + half) for x, y in zip(grid["x"][sel], grid["y"][sel])]
        if not boxes:
            continue
        poly = unary_union(boxes).simplify(half / 2)

        def to_ll(coords, _g=grid):
            lat, lon = geo.to_latlon(coords[:, 0], coords[:, 1], _g["lat0"], _g["lon0"])
            return np.c_[lon, lat]

        feats.append({"type": "Feature", "properties": {"horizon_min": h},
                      "geometry": mapping(shapely.transform(poly, to_ll))})
    return {"type": "FeatureCollection", "features": feats}


def cells_list(grid: dict) -> list[dict]:
    sel = grid["arrival"] <= HORIZONS[-1]
    lat, lon = geo.to_latlon(grid["x"][sel], grid["y"][sel], grid["lat0"], grid["lon0"])
    return [{"lat": round(float(a), 5), "lon": round(float(b), 5), "arrival_min": round(float(t), 1)}
            for a, b, t in zip(lat, lon, grid["arrival"][sel])]


def arrival_at(grid: dict, lat: float, lon: float) -> float:
    """Arrival time (min) of the grid cell containing a point; inf if outside the grid."""
    x, y = geo.to_xy(lat, lon, grid["lat0"], grid["lon0"])
    c = grid["cell_m"]
    h, w = grid["shape"]
    col = int(round((float(x) - grid["x"].min()) / c))
    row = int(round((float(y) - grid["y"].min()) / c))
    if 0 <= row < h and 0 <= col < w:
        return float(grid["arrival"][row * w + col])
    return float("inf")
