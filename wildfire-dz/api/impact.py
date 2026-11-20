"""Villages within 15 km of a fire: minutes left, status and which way to leave."""
from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd

from api.predictor import arrival_at
from core import geo
from core.config import load_config, repo_path

STUB_STEP_DEG = 0.03  # ~3 km lattice of fake villages when the real places file is missing


@lru_cache(maxsize=1)
def real_places() -> pd.DataFrame | None:
    p = repo_path(load_config()["paths"]["places"])
    if not p.exists():
        return None
    df = pd.read_parquet(p) if p.suffix == ".parquet" else pd.read_csv(p)
    df = df[["id", "name", "lat", "lon"]].copy()
    df["id"] = df["id"].astype(str)
    return df


def places_near(lat: np.ndarray, lon: np.ndarray, radius_km: float) -> pd.DataFrame:
    pad = radius_km / 100 + 0.05
    lat_min, lat_max, lon_min, lon_max = lat.min() - pad, lat.max() + pad, lon.min() - pad, lon.max() + pad
    df = real_places()
    if df is None:  # STUB: deterministic fake villages so the frontend has something to show
        i = np.arange(np.floor(lat_min / STUB_STEP_DEG), np.ceil(lat_max / STUB_STEP_DEG))
        j = np.arange(np.floor(lon_min / STUB_STEP_DEG), np.ceil(lon_max / STUB_STEP_DEG))
        ii, jj = np.meshgrid(i, j)
        ii, jj = ii.ravel().astype(int), jj.ravel().astype(int)
        return pd.DataFrame({"id": [f"stub:{a}_{b}" for a, b in zip(ii, jj)],
                             "name": [f"Stub village {a % 1000}-{b % 1000}" for a, b in zip(ii, jj)],
                             "lat": ii * STUB_STEP_DEG, "lon": jj * STUB_STEP_DEG})
    return df[df.lat.between(lat_min, lat_max) & df.lon.between(lon_min, lon_max)]


def status_for(minutes: float | None, cfg: dict) -> str:
    s = cfg["status"]
    if minutes is None or minutes > s["get_ready_max_min"]:
        return "safe"
    return "leave_now" if minutes < s["leave_now_max_min"] else "get_ready"


def villages_at_risk(burn_lat: np.ndarray, burn_lon: np.ndarray, grid: dict, cfg: dict | None = None) -> list[dict]:
    """Computed (non-sticky) status per village. The sticky rule is applied in api/alerts.py."""
    cfg = cfg or load_config()
    radius_km = cfg["villages"]["radius_km"]
    out = []
    for p in places_near(burn_lat, burn_lon, radius_km).itertuples(index=False):
        d = geo.haversine_m(p.lat, p.lon, burn_lat, burn_lon)
        k = int(np.argmin(d))
        dist_km = float(d[k]) / 1000
        if dist_km > radius_km:
            continue
        t = arrival_at(grid, p.lat, p.lon)
        minutes = int(round(t)) if np.isfinite(t) and t <= 24 * 60 else None
        fire_deg = float(geo.bearing_deg(p.lat, p.lon, burn_lat[k], burn_lon[k]))
        leave_deg = (fire_deg + 180) % 360
        out.append({"id": p.id, "name": p.name, "lat": round(float(p.lat), 5), "lon": round(float(p.lon), 5),
                    "distance_km": round(dist_km, 2), "minutes_left": minutes,
                    "status": status_for(minutes, cfg),
                    "fire_direction": geo.compass8(fire_deg), "leave_toward": geo.compass8(leave_deg),
                    "leave_toward_deg": round(leave_deg, 1)})
    out.sort(key=lambda v: (v["minutes_left"] is None, v["minutes_left"] or 0, v["distance_km"]))
    return out
