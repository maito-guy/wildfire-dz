"""Pass-by-pass replay of the held-out fires.

Reads data/out/replay_passes.parquet (schema in docs/contracts.md). Until that exists, serves ONE
synthetic fire, clearly flagged stub=true, so the dashboard can be built. It is not real data.
"""
from __future__ import annotations

import datetime as dt

import numpy as np
import pandas as pd

from core import geo
from core.config import load_config, repo_path

STUB_ID = "stub_synthetic"


def _real() -> pd.DataFrame | None:
    p = repo_path(load_config()["paths"]["replay_passes"])
    return pd.read_parquet(p) if p.exists() else None


def list_fires() -> list[dict]:
    cfg = load_config()
    df = _real()
    if df is None:
        return [{"fire_id": STUB_ID, "name": "STUB synthetic fire (not real data)", "n_passes": 8, "stub": True}]
    out = []
    for key, g in df.groupby("holdout"):
        out.append({"fire_id": key, "name": cfg["holdouts"].get(key, {}).get("name", key),
                    "n_passes": int(g["t"].nunique()), "stub": False})
    return out


def get_passes(fire_id: str) -> dict | None:
    df = _real()
    if df is None:
        return _stub() if fire_id == STUB_ID else None
    g = df[df["holdout"] == fire_id]
    if g.empty:
        return None
    passes = []
    for t, p in g.sort_values("t").groupby("t"):
        passes.append({"t": pd.Timestamp(t).isoformat(),
                       "satellite": str(p["satellite"].iloc[0]) if "satellite" in p else None,
                       "burning": [{"lat": float(a), "lon": float(b)} for a, b in zip(p.lat, p.lon)]})
    name = load_config()["holdouts"].get(fire_id, {}).get("name", fire_id)
    return {"fire_id": fire_id, "name": name, "stub": False, "passes": passes}


def _stub() -> dict:
    """A blob growing east-north-east, 8 passes, mixed 50 min / ~6 h gaps like real VIIRS timing."""
    lat0, lon0 = 36.65, 4.10
    t0 = dt.datetime(2021, 8, 9, 1, 30, tzinfo=dt.UTC)
    gaps = [0, 50, 360, 50, 400, 50, 360, 50]
    rng = np.random.default_rng(7)
    passes, t, r = [], t0, 300.0
    for i, g in enumerate(gaps):
        t = t + dt.timedelta(minutes=g)
        r += g * 6.0
        n = 20 + 15 * i
        ang = rng.uniform(0, 2 * np.pi, n)
        rad = r * np.sqrt(rng.uniform(0, 1, n))
        x = rad * np.cos(ang) * 1.8 + r * 0.8   # stretched and drifting east
        y = rad * np.sin(ang)
        lat, lon = geo.to_latlon(x, y, lat0, lon0)
        passes.append({"t": t.isoformat(), "satellite": ["NOAA-20", "S-NPP", "NOAA-21"][i % 3],
                       "burning": [{"lat": round(float(a), 5), "lon": round(float(b), 5)} for a, b in zip(lat, lon)]})
    return {"fire_id": STUB_ID, "name": "STUB synthetic fire (not real data)", "stub": True, "passes": passes}
