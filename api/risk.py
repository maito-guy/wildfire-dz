"""Today's fire-risk layer and the preventive flags for very-high-risk places (#28, SPEC §5, §6.2).

Reads `config.yaml → paths.risk_today` (written by `model.risk`, #27; file contract in docs/contracts.md).
Until that file exists, serves deterministic STUB cells over northern Algeria, flagged `stub: true`
(PROGRESS D-12). They are not real data.

Each place near a cell at `risk.flag_level` (very high) becomes ONE pending `preventive` flag per day in the
approval queue, through `AlertStore.flag` (source `ai_risk`, fire_id `risk_<date>`; PROGRESS C-12). A place
already flagged that day, whatever happened to the flag (sent, rejected, cancelled), is not flagged again.
"""
from __future__ import annotations

import datetime as dt
from functools import lru_cache

import numpy as np
import pandas as pd

from api import impact, stub_places
from api.alerts import store
from core import geo
from core.config import load_config, repo_path

LEVELS = ("low", "moderate", "high", "very_high")
RANK = {lv: i for i, lv in enumerate(LEVELS)}
COLUMNS = ("date", "lat", "lon", "score", "level", "top_factors")

# STUB geometry: rough Algerian coastline (lon -> northernmost land lat) and a few hot spots. Not real data.
_COAST_LON = [-1.8, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.6]
_COAST_LAT = [35.1, 35.5, 35.9, 36.45, 36.6, 36.75, 36.9, 36.75, 37.0, 36.95, 36.9]
_HOT = [  # (lat, lon, strength, width_deg)
    (36.65, 4.10, 0.75, 0.35),   # Kabylie
    (36.75, 5.90, 0.70, 0.30),   # Jijel
    (36.75, 8.20, 0.65, 0.30),   # El Tarf
    (36.05, 1.60, 0.50, 0.35),   # Ouarsenis
    (34.95, -1.30, 0.45, 0.30),  # Tlemcen
    (36.72, 5.05, 0.55, 0.20),   # Bejaia
    (36.88, 6.90, 0.55, 0.22),   # Skikda
    (36.45, 7.45, 0.50, 0.20),   # Guelma
    (36.55, 2.45, 0.45, 0.18),   # Tipaza / Cherchell
    (36.30, 2.75, 0.45, 0.20),   # Medea / Blida atlas
    (36.20, 8.00, 0.40, 0.20),   # Souk Ahras
    (35.40, 0.15, 0.35, 0.25),   # Mascara
]
_FACTORS = ("wind", "dryness", "past fires", "heat", "forest fuel")


def _rank_of(level: str) -> int:
    return RANK.get(str(level), 0)


@lru_cache(maxsize=2)
def _read(path: str, mtime: float) -> pd.DataFrame:
    df = pd.read_parquet(path)
    missing = [c for c in COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path} is missing columns {missing} (docs/contracts.md, risk_today.parquet)")
    df = df[list(COLUMNS)].copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df["top_factors"] = df["top_factors"].map(_factors)
    return df


def _factors(x) -> list[str]:
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return []
    if isinstance(x, str):
        return [f.strip() for f in x.split(";") if f.strip()]
    return [str(f) for f in x]


def _level_for(score: np.ndarray, cfg: dict) -> np.ndarray:
    th = cfg["risk"]["levels"]
    return np.select([score >= th["very_high"], score >= th["high"], score >= th["moderate"]],
                     ["very_high", "high", "moderate"], "low")


def stub_cells(cfg: dict, date: str) -> pd.DataFrame:
    """Deterministic fake risk cells over northern Algeria (land only, roughly). STUB, not real data."""
    step = cfg["risk"]["stub_step_deg"]
    lat_min = cfg["scope"]["lat_min"]
    lats = np.arange(lat_min + step / 2, max(_COAST_LAT), step)
    lons = np.arange(_COAST_LON[0] + step / 2, _COAST_LON[-1], step)
    la, lo = np.meshgrid(lats, lons)
    la, lo = la.ravel(), lo.ravel()
    land = la <= np.interp(lo, _COAST_LON, _COAST_LAT) - step / 2
    la, lo = la[land], lo[land]
    # Same day, same map; a new day moves things a little. Value noise breaks the grid and the round blobs.
    seed = int(date.replace("-", "")) % 9973
    rough = stub_places.fractal_noise(la, lo, seed)
    patch = stub_places.fractal_noise(la, lo, seed + 50)  # forest vs bare land
    past = sum(s * np.exp(-((la - a) ** 2 + (lo - b) ** 2) / (2 * w * w)) for a, b, s, w in _HOT)
    past = past * (0.55 + 0.9 * rough)
    wind = 0.5 + 0.5 * np.sin(lo * 1.7 + 0.3 + seed % 7)
    dry = 0.5 + 0.5 * np.cos(la * 2.3)
    heat = 0.5 + 0.5 * np.sin(la * 1.1 + lo * 0.7)
    fuel = np.clip(1.4 * (la - lat_min) / (max(_COAST_LAT) - lat_min), 0, 1) * (0.4 + 0.9 * patch)
    jitter = stub_places.hash01(np.round(la / step).astype(np.int64), np.round(lo / step).astype(np.int64), seed)
    score = np.clip(0.02 + past + 0.10 * wind + 0.06 * dry + 0.04 * heat + 0.14 * fuel
                    + 0.18 * (rough - 0.5) + 0.06 * (jitter - 0.5), 0, 0.99)
    contrib = np.stack([0.08 * wind, 0.06 * dry, past, 0.04 * heat, 0.06 * fuel], axis=1)
    order = np.argsort(-contrib, axis=1)[:, :3]
    return pd.DataFrame({"date": date, "lat": np.round(la, 5), "lon": np.round(lo, 5),
                         "score": np.round(score, 3), "level": _level_for(score, cfg),
                         "top_factors": [[_FACTORS[i] for i in row] for row in order]})


def load(cfg: dict | None = None) -> tuple[pd.DataFrame, bool, dt.datetime | None]:
    """Today's rows (the latest date in the file), whether they are stub, and when the file was written."""
    cfg = cfg or load_config()
    p = repo_path(cfg["paths"]["risk_today"])
    if not p.exists():
        return stub_cells(cfg, dt.datetime.now(dt.UTC).date().isoformat()), True, None
    mtime = p.stat().st_mtime
    df = _read(str(p), mtime)
    if not df.empty:
        df = df[df["date"] == df["date"].max()]
    return df, False, dt.datetime.fromtimestamp(mtime, dt.UTC)


def simplify(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Merge cells onto the display lattice (highest score wins) and keep levels >= min_level_shown."""
    if df.empty:
        return df.assign(ix=pd.Series(dtype=int), jx=pd.Series(dtype=int))
    d = cfg["risk"]["display_cell_deg"]
    g = df.assign(ix=np.floor(df["lat"] / d).astype(int), jx=np.floor(df["lon"] / d).astype(int))
    g = g.loc[g.groupby(["ix", "jx"])["score"].idxmax()].copy()
    g["lat"] = np.round((g["ix"] + 0.5) * d, 5)
    g["lon"] = np.round((g["jx"] + 0.5) * d, 5)
    keep = g["level"].map(_rank_of) >= _rank_of(cfg["risk"]["min_level_shown"])
    return g[keep].sort_values("score", ascending=False).reset_index(drop=True)


def flagged_places(cells: pd.DataFrame, cfg: dict) -> list[dict]:
    """Places within place_radius_km of a cell at flag_level, highest score first, at least
    min_flag_spacing_km apart, at most max_flags."""
    rc = cfg["risk"]
    hot = cells[cells["level"].map(_rank_of) >= _rank_of(rc["flag_level"])]
    if hot.empty:
        return []
    radius_m = rc["place_radius_km"] * 1000
    places = impact.real_places()
    out: list[dict] = []
    if places is None:  # STUB: one fake place at the centre of each very-high cell
        stub_names = stub_places.names(hot["ix"].to_numpy(), hot["jx"].to_numpy())
        for c, name in zip(hot.itertuples(index=False), stub_names):
            out.append({"id": f"stub-risk:{c.ix}_{c.jx}", "name": name,
                        "lat": float(c.lat), "lon": float(c.lon), "distance_km": 0.0, "score": float(c.score),
                        "level": str(c.level), "top_factors": list(c.top_factors)})
    else:
        pad = rc["place_radius_km"] / 100 + rc["display_cell_deg"]
        near = places[places.lat.between(hot.lat.min() - pad, hot.lat.max() + pad)
                      & places.lon.between(hot.lon.min() - pad, hot.lon.max() + pad)]
        if not near.empty:
            d = geo.haversine_m(near.lat.to_numpy()[:, None], near.lon.to_numpy()[:, None],
                                hot.lat.to_numpy()[None, :], hot.lon.to_numpy()[None, :])
            score = np.where(d <= radius_m, hot.score.to_numpy()[None, :], -1.0)
            best = np.argmax(score - d * 1e-9, axis=1)  # highest score, then nearest
            for i, p in enumerate(near.itertuples(index=False)):
                k = int(best[i])
                if score[i, k] < 0:
                    continue
                c = hot.iloc[k]
                out.append({"id": str(p.id), "name": str(p.name), "lat": round(float(p.lat), 5),
                            "lon": round(float(p.lon), 5), "distance_km": round(float(d[i, k]) / 1000, 2),
                            "score": float(c.score), "level": str(c.level), "top_factors": list(c.top_factors)})
    out.sort(key=lambda v: (-v["score"], v["distance_km"], v["name"]))
    chosen: list[dict] = []  # greedy: skip places too close to a better one, so one hot valley is not 10 flags
    for v in out:
        if len(chosen) >= rc["max_flags"]:
            break
        if all(geo.haversine_m(v["lat"], v["lon"], c["lat"], c["lon"]) >= rc["min_flag_spacing_km"] * 1000
               for c in chosen):
            chosen.append(v)
    return chosen


def sync_flags(places: list[dict], date: str, data_age_min: int) -> list[dict]:
    """One pending preventive flag per place and day; attaches `alert_id` and `alert_status` to each place."""
    fire_id = f"risk_{date}"
    scenario_time = dt.datetime.fromisoformat(date).replace(tzinfo=dt.UTC)
    for v in places:
        a = next((x for x in reversed(store.alerts.values())
                  if x["fire_id"] == fire_id and x["village_id"] == v["id"]), None)
        if a is None:
            a = store.flag(fire_id, v, "preventive", "ai_risk", scenario_time, data_age_min)
        v["alert_id"], v["alert_status"] = a["id"], a["status"]
    return places


def today(cfg: dict | None = None) -> dict:
    """The `GET /risk` answer (docs/contracts.md). Creates the day's preventive flags on first call."""
    cfg = cfg or load_config()
    df, stub, written = load(cfg)
    date = str(df["date"].iloc[0]) if not df.empty else dt.datetime.now(dt.UTC).date().isoformat()
    age = int((dt.datetime.now(dt.UTC) - written).total_seconds() // 60) if written else 0
    cells = simplify(df, cfg)
    places = sync_flags(flagged_places(cells, cfg), date, max(0, age))
    return {
        "date": date, "stub": stub, "generated_at": written, "cell_deg": cfg["risk"]["display_cell_deg"],
        "flag_level": cfg["risk"]["flag_level"],
        "cells": [{"lat": float(c.lat), "lon": float(c.lon), "score": float(c.score), "level": str(c.level)}
                  for c in cells.itertuples(index=False)],
        "places": places,
    }
