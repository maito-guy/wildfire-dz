"""Turn a fire mask into 1 h / 2 h zones and per-cell arrival times. Model A/B now; C plugs in later.

Fail-safe: if C is asked for and fails (or is not wired), we answer with B and say why. Never nothing.
"""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
import shapely
from shapely.geometry import box, mapping, shape
from shapely.ops import unary_union

from core import geo
from core.config import load_config, repo_path
from model import baselines

HORIZONS = (60, 120)


@lru_cache(maxsize=1)
def manifest() -> dict:
    p = repo_path(load_config()["paths"]["artifacts"]) / "api_manifest.json"
    return json.loads(p.read_text()) if p.exists() else {}


def rate_for(model: str, cfg: dict) -> float:
    m = manifest().get("rate_m_per_min", {})
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


def run_model(model: str, lat, lon, wind_kmh, wind_from, cfg) -> tuple[str, str | None, dict]:
    """Returns (model_used, fallback_reason, grid)."""
    chosen, reason = model, None
    if model == "C" or (model == "auto" and manifest().get("model_c")):
        # C needs per-cell terrain/fuel/weather features in the API (issue: AI export-to-API).
        chosen, reason = "B", "model C not wired into the API yet; fail-safe to B"
    elif model == "auto":
        chosen = "B"
    grid = baselines.arrival_grid(lat, lon, chosen, rate_for(chosen, cfg), wind_kmh, wind_from, cfg)
    return chosen, reason, grid


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
