"""Wind is uncertain: predict with several possible winds and say how much they agree.

Nobody knows the exact wind near a fire 1-2 h ahead (gusts, valleys, the fire's own wind). So C is
not asked once with one wind, but once per wind scenario around the forecast (direction +/- a few
tens of degrees, speed x 0.7 .. 1.3, see config.yaml -> wind_uncertainty). For every cell this gives:

  prob_mean   mean P(burning within g) over the scenarios
  agreement   share of scenarios that put the cell inside the zone (1.0 = "in every wind")

The dashboard draws "likely" (agreement >= likely_share) and "possible" (any scenario) zones.

To test the idea honestly on the holdouts, `forecast_like` replaces the real (ERA5) wind with a
noisy one, like a forecast that is wrong by about as much as forecasts are.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DIR_COLS = ("wind_from_2h", "wind_dir_now")
SPEED_COLS = ("wind_speed_10m", "wind_speed_2h", "wind_gusts_10m", "gust_max_2h")
# every feature that carries wind; a no-wind model drops all of them
WIND_FEATURES = ("wind_speed_10m", "wind_gusts_10m", "wind_dir_now", "wind_speed_2h", "wind_from_2h",
                 "gust_max_2h", "downwind_cos", "rate_b", "wind_along")


def scenarios(cfg: dict) -> list[tuple[float, float]]:
    w = cfg["wind_uncertainty"]
    return [(float(d), float(f)) for d in w["dir_offsets_deg"] for f in w["speed_factors"]]


def with_wind(df: pd.DataFrame, cfg: dict, d_deg, factor) -> pd.DataFrame:
    """Rows as if the wind came from d_deg further round and blew `factor` times as hard.
    d_deg and factor may be scalars or one value per row. Needs bearing_deg (data step 5)."""
    c = cfg["columns"]
    if "bearing_deg" not in df:
        raise KeyError("bearing_deg missing: rebuild the table with data step 5 (it adds it)")
    out = df.copy()
    d = np.asarray(d_deg, dtype=float)
    f = np.asarray(factor, dtype=float)
    for col in DIR_COLS:
        if col in out:
            out[col] = (out[col].to_numpy(dtype=float) + d) % 360
    for col in SPEED_COLS:
        if col in out:
            out[col] = out[col].to_numpy(dtype=float) * f
    wind_to = (out["wind_from_2h"].to_numpy(dtype=float) + 180) % 360
    out[c["downwind_cos"]] = np.cos(np.radians(out["bearing_deg"].to_numpy(dtype=float) - wind_to))
    return out


def forecast_like(df: pd.DataFrame, cfg: dict, seed: int = 0) -> pd.DataFrame:
    """Replace the real wind with a 'forecast' that is off by a random amount, the same for every
    cell of one pass (a forecast is wrong for the whole fire at once, not cell by cell)."""
    w = cfg["wind_uncertainty"]["forecast_error"]
    rng = np.random.default_rng(seed)
    key = df[cfg["columns"]["fire_id"]].astype(str) + "|" + df["pass_idx"].astype(str)
    codes, uniq = pd.factorize(key)
    d = rng.normal(0, w["dir_sd_deg"], len(uniq))[codes]
    f = np.exp(rng.normal(0, w["speed_log_sd"], len(uniq)))[codes]
    return with_wind(df, cfg, d, f)


def ensemble(model, df: pd.DataFrame, cfg: dict, thr: float) -> dict[str, np.ndarray]:
    """C under every wind scenario: mean probability and the share of scenarios over thr."""
    probs = np.stack([model.predict_rows(with_wind(df, cfg, d, f), cfg) for d, f in scenarios(cfg)])
    return {"prob_mean": probs.mean(axis=0), "prob_max": probs.max(axis=0),
            "agreement": (probs >= thr).mean(axis=0)}


def blend(model_wind, model_nowind, df: pd.DataFrame, cfg: dict) -> np.ndarray:
    """Average of C with wind and C without: leans on wind when it helps, never only on it."""
    wt = float(cfg["wind_uncertainty"].get("blend_wind_weight", 0.5))
    return wt * model_wind.predict_rows(df, cfg) + (1 - wt) * model_nowind.predict_rows(df, cfg)
