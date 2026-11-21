"""Model C's advice on the replays (#52): zones and arrival times shown next to B's, never alerts.

B stays the model of record and creates every pending flag. C's answers are precomputed for every pass of the
holdout fires by `python -m model.replay_ai` (paths.replay_ai); this module only looks them up:
  - `/predict` for a replay (fire_id = holdout key, time within ai_layer.match_min of a precomputed pass)
    gets an `ai` block: "likely" and "possible" 1 h / 2 h zones (GeoJSON, like B's `zones`)
  - each village within one cell of C's cells gets `ai_minutes_left` (C's possible-level arrival)
Anything else (live fires, no file, a pass C did not cover) gives ai = None and ai_minutes_left = None.
C uses the real (ERA5) wind of that pass, not the wind sent in the request.
"""
from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
import pandas as pd

from api import predictor
from core import geo
from core.config import repo_path

LEVELS = (("likely", "likely_min"), ("possible", "possible_min"))


@lru_cache(maxsize=2)
def _table(path: str, mtime: float) -> tuple[pd.DataFrame, dict]:
    df = pd.read_parquet(path)
    df["t"] = pd.to_datetime(df["t"], utc=True)
    meta_path = repo_path(path).with_suffix(".json")
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    return df, meta


def _load(cfg: dict) -> tuple[pd.DataFrame, dict] | None:
    p = repo_path(cfg["paths"].get("replay_ai", "model/artifacts/replay_ai.parquet"))
    return _table(str(p), p.stat().st_mtime) if p.exists() else None   # mtime: a rebuilt file is reloaded


def _snap(cells: pd.DataFrame, cell_m: float) -> dict:
    """C's cells come from several fires' own grids, so their boxes overlap a little and their union is
    jagged (MBs of GeoJSON). Snap them to one 375 m lattice around the pass, most urgent answer per cell."""
    lat0, lon0 = float(cells["lat"].mean()), float(cells["lon"].mean())
    x, y = geo.to_xy(cells["lat"].to_numpy(), cells["lon"].to_numpy(), lat0, lon0)
    d = pd.DataFrame({"x": np.round(np.asarray(x) / cell_m) * cell_m, "y": np.round(np.asarray(y) / cell_m) * cell_m,
                      "likely_min": cells["likely_min"].fillna(np.inf).to_numpy(),
                      "possible_min": cells["possible_min"].fillna(np.inf).to_numpy()})
    d = d.groupby(["x", "y"], as_index=False).min()
    return {"x": d.x.to_numpy(), "y": d.y.to_numpy(), "likely_min": d.likely_min.to_numpy(),
            "possible_min": d.possible_min.to_numpy(), "cell_m": cell_m, "lat0": lat0, "lon0": lon0}


def _round_coords(geom: dict, nd: int = 5) -> dict:
    """~1 m precision is plenty for a 375 m layer and keeps the JSON small."""
    def r(c):
        return [r(x) for x in c] if isinstance(c[0], (list, tuple)) else [round(float(v), nd) for v in c]
    return {**geom, "coordinates": r(geom["coordinates"])}


def lookup(fire_id: str | None, time, cfg: dict) -> dict | None:
    """C's answer for this replay pass: {"model", "label", "time", "likely_recall", "possible_recall", "zones",
    "cells"} (cells = the DataFrame used for villages; dropped from the response), or None."""
    loaded = _load(cfg)
    if loaded is None or not fire_id:
        return None
    df, meta = loaded
    g = df[df["holdout"] == fire_id]
    if g.empty:
        return None
    times = g["t"].drop_duplicates()
    gap = (times - pd.Timestamp(time)).abs()
    if gap.min() > pd.Timedelta(minutes=float(cfg["ai_layer"]["match_min"])):
        return None
    t0 = times.iloc[int(np.argmin(gap.to_numpy()))]
    cells = g[g["t"] == t0]
    feats = []
    snapped = _snap(cells, float(cfg["grid"]["cell_m"]))
    for level, col in LEVELS:
        for f in predictor.zones_geojson(snapped | {"arrival": snapped[col]})["features"]:
            f["properties"]["confidence"] = level
            f["geometry"] = _round_coords(f["geometry"])
            feats.append(f)
    return {"model": meta.get("model", "C"), "label": cfg["ai_layer"]["label"], "time": t0.to_pydatetime(),
            "likely_recall": meta.get("likely_recall"), "possible_recall": meta.get("possible_recall"),
            "zones": {"type": "FeatureCollection", "features": feats}, "cells": cells}


def village_minutes(villages: list[dict], ai: dict | None, cfg: dict) -> dict[str, int | None]:
    """Village id -> C's possible-level minutes from the nearest of C's cells, if within one cell; else None."""
    if ai is None or not villages:
        return {}
    cells = ai["cells"]
    lat0, lon0 = float(cells["lat"].mean()), float(cells["lon"].mean())
    cx, cy = geo.to_xy(cells["lat"].to_numpy(), cells["lon"].to_numpy(), lat0, lon0)
    vx, vy = geo.to_xy(np.array([v["lat"] for v in villages]), np.array([v["lon"] for v in villages]), lat0, lon0)
    reach = 0.75 * float(cfg["grid"]["cell_m"])          # inside the cell, with room for grids from several fires
    minutes = cells["possible_min"].to_numpy()
    out = {}
    for i, v in enumerate(villages):
        d = np.hypot(np.asarray(cx) - vx[i], np.asarray(cy) - vy[i])
        j = int(np.argmin(d))
        out[v["id"]] = int(round(minutes[j])) if d[j] <= reach and np.isfinite(minutes[j]) else None
    return out


def public(ai: dict | None) -> dict | None:
    """The `ai` block of the /predict response (without the internal cells table)."""
    return None if ai is None else {k: v for k, v in ai.items() if k != "cells"}
