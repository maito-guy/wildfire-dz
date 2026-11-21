"""Fire map data: satellite detections (GET /detections) and fire history (GET /history).

Reads `paths.detections` and `paths.history_grid` (schemas in docs/contracts.md). Real data is cut to
northern Algeria (lat >= scope.lat_min; `country == "DZA"` when the column exists, else `fire_map.bbox`)
and gas flares are dropped (750 m blocks lit on many days across many years, the 02_clean.py rule).
Live FIRMS rows (paths.detections_live, #61) are served with the archive.
History comes from history_grid.parquet, else is aggregated from detections.parquet, else is a stub.
Until the data files exist, deterministic stub data over northern Algeria is served, flagged `stub: true`.

Build the history file once the detections exist:  python -m api.detections build-history
"""
from __future__ import annotations

import datetime as dt
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from core.config import load_config, repo_path

M_PER_DEG_LAT = 110_574.0
M_PER_DEG_LON_EQ = 111_320.0
FLARE_BLOCK_M = 750.0
STUB_NEWEST = pd.Timestamp("2026-08-30T12:40:00Z")   # the stub's "now": newest stub detection
RENAMES = {"sat": "satellite", "conf": "confidence", "latitude": "lat", "longitude": "lon"}


# ---------- cleaning (real data only) ----------
def flare_mask(lat, lon, t, min_days: int, min_years: int) -> np.ndarray:
    """True for detections in 750 m blocks seen on >= min_days distinct days across >= min_years years."""
    lat = np.asarray(lat, dtype=float)
    lon = np.asarray(lon, dtype=float)
    t = pd.DatetimeIndex(t)
    band = np.round(lat * 2) / 2
    by = np.floor(lat * M_PER_DEG_LAT / FLARE_BLOCK_M).astype(np.int64)
    bx = np.floor(lon * M_PER_DEG_LON_EQ * np.cos(np.radians(band)) / FLARE_BLOCK_M).astype(np.int64)
    g = pd.DataFrame({"bx": bx, "by": by, "day": t.floor("D"), "yr": t.year})
    s = g.groupby(["bx", "by"]).agg(ndays=("day", "nunique"), nyears=("yr", "nunique"))
    bad = s[(s.ndays >= min_days) & (s.nyears >= min_years)].index
    return pd.MultiIndex.from_arrays([bx, by]).isin(bad)


def clean(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Normalise column names, keep northern Algeria, drop gas flares. Returns rows sorted by time."""
    fm = cfg["fire_map"]
    df = df.rename(columns={k: v for k, v in RENAMES.items() if k in df.columns and v not in df.columns})
    missing = {"lat", "lon", "t"} - set(df.columns)
    if missing:
        raise ValueError(f"detections file lacks column(s) {sorted(missing)}")
    df = df.copy()
    df["t"] = pd.to_datetime(df["t"], utc=True)
    keep = df["lat"].to_numpy() >= cfg["scope"]["lat_min"]
    lon_min, lat_min, lon_max, lat_max = fm["bbox"]
    in_box = df["lon"].between(lon_min, lon_max).to_numpy() & df["lat"].between(lat_min, lat_max).to_numpy()
    if "country" in df.columns:  # rows without a country (live FIRMS, #61) are cut by the bbox
        c = df["country"]
        keep &= ((c == "DZA") | (c.isna() & in_box)).to_numpy()
    else:
        keep &= in_box
    if "flare" in df.columns:
        keep &= ~df["flare"].fillna(False).astype(bool).to_numpy()
    df = df[keep]
    if len(df):
        df = df[~flare_mask(df["lat"], df["lon"], df["t"], fm["flare_min_days"], fm["flare_min_years"])]
    return df.sort_values("t").reset_index(drop=True)


def build_history(df: pd.DataFrame, cell_deg: float) -> pd.DataFrame:
    """Aggregate clean detections onto a cell_deg grid: lat, lon (cell centre), count, years, first/last_year."""
    if df.empty:
        return pd.DataFrame({c: pd.Series(dtype=t) for c, t in
                             [("lat", float), ("lon", float), ("count", int), ("years", int),
                              ("first_year", int), ("last_year", int)]})
    g = pd.DataFrame({"iy": np.floor(df["lat"].to_numpy() / cell_deg).astype(np.int64),
                      "ix": np.floor(df["lon"].to_numpy() / cell_deg).astype(np.int64),
                      "yr": pd.DatetimeIndex(df["t"]).year})
    s = g.groupby(["iy", "ix"]).agg(count=("yr", "size"), years=("yr", "nunique"),
                                         first_year=("yr", "min"), last_year=("yr", "max"))
    s = s.reset_index()
    return pd.DataFrame({"lat": ((s.iy + 0.5) * cell_deg).round(5), "lon": ((s.ix + 0.5) * cell_deg).round(5),
                         "count": s["count"].astype(int), "years": s.years.astype(int),
                         "first_year": s.first_year.astype(int), "last_year": s.last_year.astype(int)})


# ---------- loading (cached per file modification time) ----------
def _path(key: str) -> Path:
    return repo_path(load_config()["paths"][key])


@lru_cache(maxsize=2)
def _read_detections(path: str, mtime: float) -> pd.DataFrame:
    return clean(pd.read_parquet(path), load_config())


@lru_cache(maxsize=2)
def _read_with_live(path: str | None, mtime: float, live: str | None, live_mtime: float) -> pd.DataFrame:
    """Archive + live FIRMS rows (#61), deduplicated (same place, minute and satellite)."""
    parts = [pd.read_parquet(p) for p in (path, live) if p]
    df = pd.concat(parts, ignore_index=True) if len(parts) > 1 else parts[0]
    df = clean(df, load_config())
    sat = next((c for c in ("satellite", "sat") if c in df.columns), None)
    k = df.lat.round(4).astype(str) + df.lon.round(4).astype(str) + df.t.dt.strftime("%Y%m%d%H%M")
    if sat:
        k = k + df[sat].astype(str)
    return df[~k.duplicated()].reset_index(drop=True)


def real_detections() -> pd.DataFrame | None:
    """The archive (`paths.detections`) plus the live FIRMS file (`paths.detections_live`) when it exists."""
    p = _path("detections")
    live_rel = load_config()["paths"].get("detections_live")
    live = repo_path(live_rel) if live_rel else None
    if live is None or not live.is_file():
        return _read_detections(str(p), p.stat().st_mtime) if p.exists() else None
    arch = (str(p), p.stat().st_mtime) if p.exists() else (None, 0.0)
    return _read_with_live(*arch, str(live), live.stat().st_mtime)


@lru_cache(maxsize=2)
def _read_history(path: str, mtime: float) -> pd.DataFrame:
    df = pd.read_parquet(path)
    missing = {"lat", "lon", "count"} - set(df.columns)
    if missing:
        raise ValueError(f"history grid file lacks column(s) {sorted(missing)}")
    return df[df["lat"] >= load_config()["scope"]["lat_min"]].reset_index(drop=True)


@lru_cache(maxsize=2)
def _history_from_detections(path: str, mtime: float, cell_deg: float) -> pd.DataFrame:
    return build_history(_read_detections(path, mtime), cell_deg)


# ---------- stub data (deterministic, not real) ----------
# (lat, lon, points, hours before STUB_NEWEST): a few fires across northern Algeria.
_STUB_FIRES = [(36.75, 5.95, 90, 2), (36.45, 7.35, 50, 11), (36.80, 8.25, 60, 30), (36.70, 4.25, 70, 60),
               (36.60, 4.90, 40, 110), (34.90, -1.40, 30, 150), (35.70, 0.60, 25, 165), (36.45, 2.85, 40, 400)]
# (lat, lon, spread_deg, points per year, years): past fire areas, heaviest in Kabylie 2021 and El Kala.
_STUB_HISTORY = [(36.65, 4.30, 0.25, 160, range(2012, 2027)), (36.70, 4.35, 0.15, 2500, [2021]),
                 (36.80, 8.20, 0.15, 120, range(2012, 2027)), (36.82, 8.30, 0.10, 900, [2022]),
                 (36.75, 5.90, 0.20, 100, range(2012, 2027)), (36.55, 5.70, 0.12, 600, [2023]),
                 (35.40, 7.10, 0.15, 400, [2021]), (36.40, 2.80, 0.20, 60, range(2012, 2027)),
                 (34.95, -1.35, 0.20, 50, range(2014, 2027)), (36.10, 1.30, 0.20, 40, range(2012, 2027))]
_SATS = ["NOAA20", "SNPP", "NOAA21"]


@lru_cache(maxsize=1)
def stub_detections() -> pd.DataFrame:
    rng = np.random.default_rng(29)
    rows = []
    for i, (lat0, lon0, n, hours) in enumerate(_STUB_FIRES):
        t = STUB_NEWEST - pd.Timedelta(hours=hours) - pd.to_timedelta(rng.integers(0, 3, n) * 100, unit="min")
        rows.append(pd.DataFrame({
            "lat": (lat0 + rng.normal(0, 0.02, n)).round(5), "lon": (lon0 + rng.normal(0, 0.03, n)).round(5),
            "t": t, "satellite": [_SATS[(i + k) % 3] for k in range(n)],
            "frp": rng.gamma(2.0, 8.0, n).round(1), "confidence": "n",
            "daynight": ["D" if 6 <= h < 18 else "N" for h in pd.DatetimeIndex(t).hour]}))
    return pd.concat(rows, ignore_index=True).sort_values("t").reset_index(drop=True)


@lru_cache(maxsize=1)
def stub_history(cell_deg: float) -> pd.DataFrame:
    rng = np.random.default_rng(2012)
    parts = []
    for lat0, lon0, spread, n, years in _STUB_HISTORY:
        for yr in years:
            parts.append(pd.DataFrame({"lat": lat0 + rng.normal(0, spread * 0.5, n),
                                       "lon": lon0 + rng.normal(0, spread, n),
                                       "t": pd.Timestamp(f"{yr}-08-01T12:00:00Z")}))
    return build_history(pd.concat(parts, ignore_index=True), cell_deg)


# ---------- API answers ----------
def _none(v):
    return None if pd.isna(v) else v


def detections(since: dt.datetime | None = None, until: dt.datetime | None = None) -> dict:
    """Detections with since <= t <= until, newest first. Defaults: the default_hours before the newest one."""
    fm = load_config()["fire_map"]
    df = real_detections()
    stub = df is None
    if stub:
        df = stub_detections()
    newest = df["t"].max() if len(df) else None
    end = pd.Timestamp(until) if until else (newest if newest is not None else pd.Timestamp.now(tz="UTC"))
    start = pd.Timestamp(since) if since else end - pd.Timedelta(hours=fm["default_hours"])
    if start > end:
        raise ValueError("since must be before until")
    sel = df[(df["t"] >= start) & (df["t"] <= end)].sort_values("t", ascending=False)
    truncated = len(sel) > fm["max_points"]
    sel = sel.head(fm["max_points"])
    cols = {c: (sel[c].tolist() if c in sel.columns else [None] * len(sel))
            for c in ("satellite", "frp", "confidence", "daynight")}
    out = [{"lat": float(a), "lon": float(b), "t": t.to_pydatetime(),
            "satellite": _none(s), "frp": _none(f), "confidence": _none(c), "daynight": _none(d)}
           for a, b, t, s, f, c, d in zip(sel["lat"], sel["lon"], sel["t"], cols["satellite"], cols["frp"],
                                          cols["confidence"], cols["daynight"])]
    return {"stub": stub, "newest": newest.to_pydatetime() if newest is not None else None,
            "since": start.to_pydatetime(), "until": end.to_pydatetime(), "count": len(out),
            "truncated": truncated, "detections": out}


def history() -> dict:
    """Fire history grid over the whole archive (2012 onward), one row per cell with any detection."""
    cell = float(load_config()["fire_map"]["history_cell_deg"])
    grid_p, det_p = _path("history_grid"), _path("detections")
    if grid_p.exists():
        df, source = _read_history(str(grid_p), grid_p.stat().st_mtime), "grid"
    elif det_p.exists():
        df, source = _history_from_detections(str(det_p), det_p.stat().st_mtime, cell), "detections"
    else:
        df, source = stub_history(cell), "stub"
    years = df["years"].tolist() if "years" in df.columns else [None] * len(df)
    last = df["last_year"].tolist() if "last_year" in df.columns else [None] * len(df)
    first_year = int(df["first_year"].min()) if "first_year" in df.columns and len(df) else None
    cells = [{"lat": float(a), "lon": float(b), "count": int(n), "years": _none(y), "last_year": _none(ly)}
             for a, b, n, y, ly in zip(df["lat"], df["lon"], df["count"], years, last)]
    return {"stub": source == "stub", "source": source, "cell_deg": cell, "first_year": first_year,
            "last_year": int(max(x for x in last if x is not None)) if any(x is not None for x in last) else None,
            "max_count": int(df["count"].max()) if len(df) else 0, "cells": cells}


def main(argv: list[str]) -> int:
    if argv != ["build-history"]:
        print("usage: python -m api.detections build-history", file=sys.stderr)
        return 2
    df = real_detections()
    if df is None:
        print(f"no detections file at {_path('detections')}", file=sys.stderr)
        return 1
    out = build_history(df, float(load_config()["fire_map"]["history_cell_deg"]))
    out.to_parquet(_path("history_grid"))
    print(f"{len(df):,} clean detections -> {len(out):,} history cells -> {_path('history_grid')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
