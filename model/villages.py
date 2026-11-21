"""Village scoring on the held-out fires: is the predicted time-to-arrival right, and early enough?

Replays each holdout pass by pass (data/out/replay_passes.parquet). At every pass, each model
predicts the minutes until the fire reaches every village within villages.radius_km of the fire.

Real arrival: the first pass with a burning pixel within one cell (375 m) of the village. Satellites
pass 50 min to 12 h apart, so the fire really arrived somewhere in (t_prev, t_first], where t_prev
is the pass before. Scores use that window instead of pretending to know the minute.

  The alert that counts is the one still running when the fire arrived: the unbroken run of passes
  with "get ready" or worse up to the last pass before arrival (a pass saying later, or a 24 h gap,
  ends a run). An alert days earlier for a different fire does not count.
  missed_villages       reached villages where, at a pass with surely < 60 min really left (the fire
                        was seen there <= 60 min later), the model said 60 or more
                        (missed_villages_judged = villages that had such a pass at all)
  missed_any_alert      same with the 120 min "get ready" limit
  too_slow_at_last_pass_villages  at the last pass before arrival, the model said a time later
                        than the latest possible real arrival
  median_lead_min       t_arrival - start of that run, arrival = middle of the window
                        (median_lead_min_range: same with the window's two ends)
  time error            predicted minus real minutes left, at every pass with <= 6 h real time left;
                        too_slow_share = predicted later than the latest possible arrival (dangerous)
  false_alarm_villages  told "leave now" at t, but a pass at or after t + 2 h still saw it not burning

Models: A and B through the same arrival grid the API uses. C gives a time by asking its 1 h model
"burning by g minutes?" for g in C_GAPS and taking the first g over its threshold. C only has
cells near the fire (data step 7, 6 km); elsewhere it falls back to B, and the share is reported.
"B@C_x" and "C@C_x" score B and C on exactly the village-passes where C has a cell (like for like).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from core import geo
from core.config import repo_path
from model import baselines

REACH_M = 375.0
RELEVANT_MIN = 6 * 60
STREAK_BREAK_H = 24      # passes this far apart do not continue the same alert
C_GAPS = np.array([20, 30, 45, 60, 75, 90, 105, 120, 180, 240, 360, 480, 720], dtype=float)
M_PER_DEG_LAT = 110_574.0


# ---------------------------------------------------------------- truth

def nearest_m(plat, plon, blat, blon, chunk=2048):
    """Distance (m) from each place to the nearest burning point."""
    out = np.full(len(plat), np.inf)
    for i in range(0, len(blat), chunk):
        d = geo.haversine_m(plat[:, None], plon[:, None], blat[None, i:i + chunk], blon[None, i:i + chunk])
        out = np.minimum(out, d.min(axis=1))
    return out


def truth(rp: pd.DataFrame, places: pd.DataFrame, cfg: dict):
    """Villages near the fire, pass times, and each village's arrival window (t_prev, t_first]."""
    radius = cfg["villages"]["radius_km"] * 1000
    pad = cfg["villages"]["radius_km"] / 100 + 0.05
    pl = places[places.lat.between(rp.lat.min() - pad, rp.lat.max() + pad)
                & places.lon.between(rp.lon.min() - pad, rp.lon.max() + pad)]
    pl = pl[nearest_m(pl.lat.to_numpy(), pl.lon.to_numpy(), rp.lat.to_numpy(), rp.lon.to_numpy()) <= radius]
    pl = pl.reset_index(drop=True)
    plat, plon = pl.lat.to_numpy(), pl.lon.to_numpy()
    times = pd.DatetimeIndex(sorted(rp["t"].unique()))
    first_k = np.full(len(pl), -1)                    # index into `times` of the first burning pass
    for k, t in enumerate(times):
        todo = first_k < 0
        if not todo.any():
            break
        g = rp[rp.t == t]
        hit = nearest_m(plat[todo], plon[todo], g.lat.to_numpy(), g.lon.to_numpy()) <= REACH_M
        first_k[np.flatnonzero(todo)[hit]] = k
    reached = first_k >= 0
    pl["t_first"] = pd.Series(times[np.maximum(first_k, 0)]).where(reached).values
    pl["t_prev"] = pd.Series(times[np.maximum(first_k - 1, 0)]).where(first_k >= 1).values
    pl["t_first"] = pd.to_datetime(pl["t_first"], utc=True)
    pl["t_prev"] = pd.to_datetime(pl["t_prev"], utc=True)
    return pl, times


# ---------------------------------------------------------------- predictions

def wind_at(dense: pd.DataFrame | None, t, cfg: dict) -> tuple[float, float]:
    """ERA5 wind (speed, from) for this pass from the holdout rows; config default if none."""
    if dense is not None and len(dense):
        dt_min = (dense["t1"] - t).abs().dt.total_seconds() / 60
        near = dense[dt_min <= dt_min.min() + 1]
        if dt_min.min() <= 180:
            rad = np.radians(near["wind_from_2h"].to_numpy(float))
            sp = near["wind_speed_2h"].to_numpy(float)
            u, v = (sp * np.sin(rad)).mean(), (sp * np.cos(rad)).mean()
            return float(np.hypot(u, v)), float((np.degrees(np.arctan2(u, v)) + 360) % 360)
    d = cfg["weather_default"]
    return float(d["speed_kmh"]), float(d["from_deg"])


def baseline_minutes(model, rate, g, plat, plon, wind, cfg):
    from api.predictor import arrival_at  # same lookup the API uses for villages

    grid = baselines.arrival_grid(g.lat.to_numpy(), g.lon.to_numpy(), model, rate, wind[0], wind[1], cfg)
    return np.array([arrival_at(grid, a, b) for a, b in zip(plat, plon)])


def c_minutes(rows: pd.DataFrame, model, thr: float, cfg: dict) -> np.ndarray:
    """First g in C_GAPS where P(burning within g) >= thr; inf if never. Taking the first crossing
    keeps the answer consistent even where the trees are not monotone in g."""
    first = np.full(len(rows), np.inf)
    lo, hi = cfg["model"].get("short_pair_min", [20, 120])
    for g in C_GAPS:
        kind = cfg["model"]["kind_for_1h"] if lo <= g <= hi else "long"
        p = model.predict_rows(rows.assign(**{cfg["columns"]["gap_min"]: g, cfg["columns"]["kind"]: kind}), cfg)
        first = np.where(np.isinf(first) & (p >= thr), g, first)
    return first


def c_lookup(dense_t: pd.DataFrame, minutes: np.ndarray, plat, plon) -> np.ndarray:
    """Minutes for each village from the dense rows of this pass (min over fires); nan if no cell."""
    out = np.full(len(plat), np.nan)
    for _, idx in dense_t.groupby("fire_id").indices.items():
        r = dense_t.iloc[idx]
        lat0, lon0, mlon = r.grid_lat0.iat[0], r.grid_lon0.iat[0], r.grid_mlon.iat[0]
        cell = 375.0
        vix = np.floor((plon - lon0) * mlon / cell).astype(int)
        viy = np.floor((plat - lat0) * M_PER_DEG_LAT / cell).astype(int)
        key = pd.Series(minutes[idx], index=pd.MultiIndex.from_arrays([r.ix.to_numpy(), r.iy.to_numpy()]))
        key = key[~key.index.duplicated()]
        got = key.reindex(pd.MultiIndex.from_arrays([vix, viy])).to_numpy()
        out = np.where(np.isnan(out), got, np.fmin(out, got))
    return out


# ---------------------------------------------------------------- scoring

def score(pred: pd.DataFrame, pl: pd.DataFrame, cfg: dict) -> dict:
    """pred: village, t, minutes (one row per village per pass)."""
    s = cfg["status"]
    p = pred.merge(pl[["vid", "t_first", "t_prev"]], on="vid")
    p = p[p.t_first.isna() | (p.t <= p.t_prev)]                      # decisions before arrival
    leave = p.minutes < s["leave_now_max_min"]
    reached = pl[pl.t_first.notna() & pl.t_prev.notna()]             # reached after the first pass
    # Only the alert still running when the fire arrived counts: the unbroken run of passes with
    # "get ready" or worse just before arrival. An alert days earlier for another fire does not.
    r = p[p.vid.isin(reached.vid)].sort_values(["vid", "t"])
    gap_break = r.groupby("vid").t.diff() > pd.Timedelta(hours=STREAK_BREAK_H)
    brk = (~(r.minutes < s["get_ready_max_min"]) | gap_break).astype(int)
    r = r.assign(run=brk.groupby(r.vid).cumsum())
    last_run = r.groupby("vid").run.transform("max")
    # a pass saying "later" starts a new run, so a run that ended before arrival leaves this empty
    final = r[(r.run == last_run) & (r.minutes < s["get_ready_max_min"])]
    fr = final.groupby("vid").t.min().reindex(reached.vid)
    # Missed = at a pass where the real time left was surely under the limit (the fire was seen
    # there within `limit` minutes), the model said the limit or more. Villages whose passes were
    # all too far apart to tell are not judged (counted in *_judged).
    r_hi = (r.t_first - r.t).dt.total_seconds() / 60

    def missed(limit: float) -> tuple[int, int]:
        j = r[r_hi <= limit]
        return int(j[j.minutes >= limit].vid.nunique()), int(j.vid.nunique())

    missed_leave, judged_leave = missed(s["leave_now_max_min"])
    missed_ready, judged_ready = missed(s["get_ready_max_min"])
    last = r[r.t == r.groupby("vid").t.transform("max")]
    too_slow_last = int((last.minutes > (last.t_first - last.t).dt.total_seconds() / 60).sum())
    lead_lo = (reached.t_prev.values - fr.values) / np.timedelta64(1, "m")
    lead_hi = (reached.t_first.values - fr.values) / np.timedelta64(1, "m")
    lead_mid = (lead_lo + lead_hi) / 2

    q = p[p.t_first.notna()].copy()
    q["lo"] = (q.t_prev - q.t).dt.total_seconds() / 60
    q["hi"] = (q.t_first - q.t).dt.total_seconds() / 60
    q = q[(q.hi <= RELEVANT_MIN) & np.isfinite(q.minutes)]
    err = q.minutes - (q.lo + q.hi) / 2

    warned = p[leave]
    fa = warned.t_first.isna() | (warned.t_prev >= warned.t + pd.Timedelta(minutes=120))
    fa_v = warned[fa].vid.nunique()
    has_lead = np.isfinite(lead_mid).any()
    return {
        "villages_in_area": int(len(pl)), "villages_reached": int(len(reached)),
        "missed_villages": missed_leave, "missed_villages_judged": judged_leave,
        "missed_any_alert": missed_ready, "missed_any_alert_judged": judged_ready,
        "too_slow_at_last_pass_villages": too_slow_last,
        "median_lead_min": round(float(np.nanmedian(lead_mid)), 1) if has_lead else None,
        "median_lead_min_range": [round(float(np.nanmedian(lead_lo)), 1), round(float(np.nanmedian(lead_hi)), 1)]
        if has_lead else None,
        "time_error_median_min": round(float(err.median()), 1) if len(err) else None,
        "time_error_abs_median_min": round(float(err.abs().median()), 1) if len(err) else None,
        "too_slow_share": round(float((q.minutes > q.hi).mean()), 4) if len(q) else None,
        "false_alarm_villages": int(fa_v), "villages_told_leave_now": int(warned.vid.nunique()),
        "status": "measured",
    }


def evaluate_villages(cfg: dict, thresholds: dict, boosters: dict, replay_key: str = "replay_passes",
                      dense_key: str = "holdout_dense", keys: set[str] | None = None) -> dict:
    """{holdout: {model: metrics}} or {} if the replay/places files are missing.
    replay_key / dense_key: entries of config paths (crossval.py passes events_replay / events_dense);
    keys: score only these events (default: every one in the replay file)."""
    rp_path, pl_path = repo_path(cfg["paths"][replay_key]), repo_path(cfg["paths"]["places"])
    if not (rp_path.exists() and pl_path.exists()):
        return {}
    dense_path = repo_path(cfg["paths"].get(dense_key, f"data/out/{dense_key}.parquet"))
    filters = [("holdout", "in", sorted(keys))] if keys else None
    dense_all = pd.read_parquet(dense_path, filters=filters) if dense_path.exists() else None
    if dense_all is not None:
        dense_all["t1"] = pd.to_datetime(dense_all["t1"], utc=True)
    rp_all = pd.read_parquet(rp_path)
    rp_all["t"] = pd.to_datetime(rp_all["t"], utc=True)
    if keys:
        rp_all = rp_all[rp_all.holdout.isin(keys)]
    places = pd.read_parquet(pl_path)
    out = {}
    for key, rp in rp_all.groupby("holdout"):
        pl, times = truth(rp, places, cfg)
        pl["vid"] = np.arange(len(pl))
        plat, plon = pl.lat.to_numpy(), pl.lon.to_numpy()
        dense = dense_all[dense_all.holdout == key] if dense_all is not None else None
        c_min = {}
        if dense is not None:
            for tag, model in boosters.items():
                th = thresholds[f"C_{tag}"]
                c_min[tag] = c_minutes(dense, model, th.get("prob_time", th["prob"]), cfg)
        # "<m>@C_<tag>": the same model scored only where C has a cell, for a like-for-like comparison
        rows = {m: [] for m in ["A", "B"] + [f"C_{t}" for t in c_min]
                + [f"{x}@C_{t}" for t in c_min for x in ("B", "C")]}
        c_fallback = {t: [0, 0] for t in c_min}
        radius = cfg["villages"]["radius_km"] * 1000
        for t, g in rp.groupby("t", sort=True):
            near = nearest_m(plat, plon, g.lat.to_numpy(), g.lon.to_numpy()) <= radius
            if not near.any():
                continue
            vid = pl.vid.to_numpy()[near]
            wind = wind_at(dense, t, cfg)
            mins = {}
            for m in ("A", "B"):
                mins[m] = baseline_minutes(m, thresholds[m]["rate_m_per_min"], g, plat[near], plon[near], wind, cfg)
                rows[m].append(pd.DataFrame({"vid": vid, "t": t, "minutes": mins[m]}))
            for tag, cm in c_min.items():
                sel = (dense.t1 == t).to_numpy()
                got = c_lookup(dense[sel], cm[sel], plat[near], plon[near]) if sel.any() else np.full(near.sum(), np.nan)
                fb = np.isnan(got)
                c_fallback[tag][0] += int(fb.sum())
                c_fallback[tag][1] += len(got)
                rows[f"C_{tag}"].append(pd.DataFrame({"vid": vid, "t": t, "minutes": np.where(fb, mins["B"], got)}))
                rows[f"C@C_{tag}"].append(pd.DataFrame({"vid": vid[~fb], "t": t, "minutes": got[~fb]}))
                rows[f"B@C_{tag}"].append(pd.DataFrame({"vid": vid[~fb], "t": t, "minutes": mins["B"][~fb]}))
        out[key] = {}
        for m, parts in rows.items():
            res = score(pd.concat(parts, ignore_index=True), pl, cfg) if parts else {"status": "no passes"}
            if m.startswith("C_") and m[2:] in c_fallback:
                n_fb, n = c_fallback[m[2:]]
                res["fallback_to_B_share"] = round(n_fb / max(n, 1), 4)
            out[key][m] = res
    return out


def load_boosters(cfg: dict) -> dict:
    from model import ensemble

    return ensemble.load_all(repo_path(cfg["paths"]["artifacts"]))
