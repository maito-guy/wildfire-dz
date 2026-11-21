"""Load train.parquet, split by whole fires, pick feature columns."""
from __future__ import annotations

import numpy as np
import pandas as pd

from core.config import repo_path


def load_table(cfg: dict, path: str | None = None) -> pd.DataFrame:
    p = repo_path(path or cfg["paths"]["train_table"])
    if not p.exists():
        raise FileNotFoundError(f"{p} not found. Run the data pipeline (data/README.md) first.")
    df = pd.read_parquet(p)
    check_columns(df, cfg)
    return df


def check_columns(df: pd.DataFrame, cfg: dict) -> None:
    c = cfg["columns"]
    needed = [v for k, v in c.items() if k != "id_like"]
    missing = [col for col in needed if col not in df.columns]
    if missing:
        raise KeyError(
            f"train table is missing {missing}. Fix `columns:` in config.yaml. "
            f"Available: {sorted(df.columns)}"
        )


def holdout_fire_ids(df: pd.DataFrame, cfg: dict, events: dict | None = None) -> dict[str, set]:
    """A fire belongs to an event if any of its rows falls inside the event's time window and bbox.
    events: {key: {start, end, bbox}}; default config.yaml -> holdouts (crossval.py passes crossval.events)."""
    c = cfg["columns"]
    t = pd.to_datetime(df[c["t1"]], utc=True)
    out: dict[str, set] = {}
    for key, h in (cfg["holdouts"] if events is None else events).items():
        lon_min, lat_min, lon_max, lat_max = h["bbox"]
        start = pd.Timestamp(h["start"], tz="UTC")
        end = pd.Timestamp(h["end"], tz="UTC") + pd.Timedelta(days=1)
        m = (
            (t >= start) & (t < end)
            & df[c["lat"]].between(lat_min, lat_max)
            & df[c["lon"]].between(lon_min, lon_max)
        )
        out[key] = set(df.loc[m, c["fire_id"]].unique())
    return out


def split(df: pd.DataFrame, cfg: dict, countries: list[str] | None = None):
    """Returns (train, val, holdouts{name: df}). Val = random whole training fires."""
    c = cfg["columns"]
    hold = holdout_fire_ids(df, cfg)
    all_hold = set().union(*hold.values()) if hold else set()
    rest = df[~df[c["fire_id"]].isin(all_hold)]
    if countries:
        rest = rest[rest[c["country"]].isin(countries)]
    fires = rest[c["fire_id"]].unique()
    rng = np.random.default_rng(cfg["model"]["seed"])
    n_val = max(1, int(len(fires) * cfg["model"]["val_fraction"]))
    val_ids = set(rng.choice(fires, size=n_val, replace=False)) if len(fires) > 1 else set()
    train = rest[~rest[c["fire_id"]].isin(val_ids)]
    val = rest[rest[c["fire_id"]].isin(val_ids)]
    holdouts = {k: df[df[c["fire_id"]].isin(ids)] for k, ids in hold.items()}
    return train, val, holdouts


# Built from other columns in to_matrix, never read from the table. They put the physics of
# baselines A and B in front of the trees: "how fast would the fire have to run to get here?"
DERIVED = ("rate_a", "rate_b", "rate_burned", "wind_along", "is_short")


def feature_columns(df: pd.DataFrame, cfg: dict) -> list[str]:
    drop = set(cfg["columns"]["id_like"]) | {cfg["columns"]["kind"]} | set(DERIVED)
    drop |= set(cfg["model"].get("drop_features", []))
    return [col for col in df.columns if col not in drop and pd.api.types.is_numeric_dtype(df[col])]


def to_matrix(df: pd.DataFrame, cols: list[str], cfg: dict) -> pd.DataFrame:
    """cols = raw table columns. Adds the derived features, so changing gap_min updates them."""
    from model import baselines

    c = cfg["columns"]
    X = df[[col for col in cols if col not in DERIVED]].copy()
    gap = np.maximum(df[c["gap_min"]].to_numpy(dtype=float), 1.0)
    X["rate_a"] = df[c["dist_active"]].to_numpy(dtype=float) / gap
    X["rate_b"] = baselines.required_rate(df, "B", cfg)
    if "dist_burned_m" in df:
        X["rate_burned"] = df["dist_burned_m"].to_numpy(dtype=float) / gap
    wind = df["wind_speed_2h"] if "wind_speed_2h" in df else df[c["wind_kmh"]]
    X["wind_along"] = df[c["downwind_cos"]].to_numpy(dtype=float) * wind.to_numpy(dtype=float)
    X["is_short"] = (df[c["kind"]] == cfg["model"]["kind_for_1h"]).astype(int)
    return X
