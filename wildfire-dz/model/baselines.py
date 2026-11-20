"""Baselines A (even buffer) and B (wind/slope ellipse). No training.

Both share one idea: a cell at distance d from the nearest burning cell is reached after
    t = d / (m * R)    minutes
where R is a base spread rate (m/min, tuned so >= 95 % of burned cells fall inside the zone)
and m is a direction multiplier: m = 1 for A, m = exp(wind_coef*W*cos + slope_coef*grade) for B.

Used in two places:
  * on train.parquet rows (score_table) -> evaluation and threshold tuning
  * on a live grid around a fire mask (arrival_grid) -> the API's /predict
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core import geo


def multiplier(model: str, downwind_cos, wind_kmh, uphill_grade, params: dict) -> np.ndarray:
    downwind_cos = np.asarray(downwind_cos, dtype=float)
    if model == "A":
        return np.ones_like(downwind_cos)
    b = params["baseline_b"]
    expo = b["wind_coef"] * np.asarray(wind_kmh, dtype=float) * downwind_cos
    expo = expo + b["slope_coef"] * np.asarray(uphill_grade, dtype=float)
    return np.exp(np.clip(expo, -5, 5))


def required_rate(df: pd.DataFrame, model: str, cfg: dict) -> np.ndarray:
    """Rate (m/min) a cell 'needs' to have been reached by the next pass. Lower = more likely to burn."""
    c = cfg["columns"]
    m = multiplier(model, df[c["downwind_cos"]], df[c["wind_kmh"]], df[c["uphill_grade"]], cfg["model"])
    gap = np.maximum(df[c["gap_min"]].to_numpy(dtype=float), 1.0)
    return df[c["dist_active"]].to_numpy(dtype=float) / (m * gap)


def score_table(df: pd.DataFrame, model: str, cfg: dict) -> np.ndarray:
    """Higher score = more likely to burn. Thresholding score >= -R  <=>  required rate <= R."""
    return -required_rate(df, model, cfg)


def tune_rate(df: pd.DataFrame, model: str, cfg: dict) -> float:
    """Smallest R that puts target_recall of the positive cells inside the zone."""
    pos = df[df[cfg["columns"]["label"]] == 1]
    if pos.empty:
        raise ValueError("no positive rows to tune on")
    return float(np.quantile(required_rate(pos, model, cfg), cfg["safety"]["target_recall"]))


# ---------------------------------------------------------------- live grid (API)

def arrival_grid(
    burn_lat: np.ndarray,
    burn_lon: np.ndarray,
    model: str,
    rate_m_per_min: float,
    wind_kmh: float,
    wind_from_deg: float,
    cfg: dict,
    chunk: int = 256,
) -> dict:
    """Arrival time (min) on a regular 375 m grid around the burning cells.

    Slope is 0 here until terrain is wired into the API (issue: export to API).
    Returns lat0/lon0, cell centres (x, y), arrival (1-D) and the grid shape.
    """
    cell = float(cfg["grid"]["cell_m"])
    radius = float(cfg["grid"]["max_radius_km"]) * 1000
    lat0, lon0 = float(np.mean(burn_lat)), float(np.mean(burn_lon))
    bx, by = geo.to_xy(burn_lat, burn_lon, lat0, lon0)
    # snap burning points to cells and dedupe
    bxy = np.unique(np.round(np.c_[bx, by] / cell).astype(int), axis=0) * cell
    bx, by = bxy[:, 0].astype(float), bxy[:, 1].astype(float)

    xs = np.arange(bx.min() - radius, bx.max() + radius + cell, cell)
    ys = np.arange(by.min() - radius, by.max() + radius + cell, cell)
    gx, gy = np.meshgrid(xs, ys)
    cx, cy = gx.ravel(), gy.ravel()

    to_rad = np.radians((wind_from_deg + 180.0) % 360)   # direction the wind blows toward
    ux, uy = np.sin(to_rad), np.cos(to_rad)

    arrival = np.full(cx.shape, np.inf)
    for i in range(0, len(bx), chunk):
        dx = cx[:, None] - bx[None, i:i + chunk]
        dy = cy[:, None] - by[None, i:i + chunk]
        d = np.hypot(dx, dy)
        cos = np.where(d > 0, (dx * ux + dy * uy) / np.maximum(d, 1e-9), 0.0)
        m = multiplier(model, cos, wind_kmh, 0.0, cfg["model"])
        arrival = np.minimum(arrival, (d / (m * rate_m_per_min)).min(axis=1))

    shape = gx.shape
    embers = wind_kmh > cfg["embers"]["wind_kmh"]
    if embers:
        arrival = _embers_widen(arrival.reshape(shape), ux, uy, cfg).ravel()
    return {"lat0": lat0, "lon0": lon0, "x": cx, "y": cy, "arrival": arrival,
            "shape": shape, "embers_applied": bool(embers), "cell_m": cell}


def _embers_widen(arr2d: np.ndarray, ux: float, uy: float, cfg: dict) -> np.ndarray:
    """Push each horizon zone out by `extra_rings` cells on the downwind side."""
    out = arr2d.copy()
    # grid rows go south->north (y increases with row), columns west->east
    steps = {(int(np.sign(round(ux))), int(np.sign(round(uy))))}
    for ang in (-45, 45):  # neighbouring compass directions
        a = np.radians(ang)
        rx, ry = ux * np.cos(a) - uy * np.sin(a), ux * np.sin(a) + uy * np.cos(a)
        steps.add((int(np.sign(round(rx))), int(np.sign(round(ry)))))
    steps.discard((0, 0))
    for _ in range(int(cfg["embers"]["extra_rings"])):
        src = out.copy()
        for sx, sy in steps:
            shifted = np.full_like(src, np.inf)
            h, w = src.shape
            ys0, ys1 = max(sy, 0), h + min(sy, 0)
            xs0, xs1 = max(sx, 0), w + min(sx, 0)
            shifted[ys0:ys1, xs0:xs1] = src[ys0 - sy:ys1 - sy, xs0 - sx:xs1 - sx]
            out = np.minimum(out, shifted)
    return out
