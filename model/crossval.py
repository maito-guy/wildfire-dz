"""Leave-one-year-out cross-validation on Algerian fires: every fire is tested exactly once.

For each year Y: C is trained on the other years' Algerian fires (20 % of them held back for early
stopping and the threshold), and B's spread rate is tuned two ways, then all are scored on year Y:

  B_all  rate tuned on every country's fires (what evaluate.py does today)
  B_dza  rate tuned on Algerian fires only (model.baseline_countries: [DZA])
  C      LightGBM, threshold set on its own validation fires (as in evaluate.py)

Test predictions from all years are pooled, then reported overall, per year, per region (west /
centre / east) and per named event (config.yaml -> crossval.events).

  1h    short pairs to the very next pass (the dashboard's 1 h zone), as in the scoreboard
  all   every pair, 20 min - 16 h: "is the cell flagged as reached by the time it really burned?"

Metrics: recall = share of burned cells inside the zone (catching); zone = flagged cells per burned
cell (false alarms; lower is better at equal recall); zone95 = zone size when each model is cut to
catch exactly 95 % on that slice (fair ranking comparison); auc = ranking quality.

Villages: for each named event, A / B / C of the event's year are replayed pass by pass over every
cell around it (data steps 6 and 7 with --events), as evaluate.py does for the holdouts.

  python -m model.crossval        # writes model/artifacts/crossval.json (~10-20 min)
"""
from __future__ import annotations

import datetime as dt
import json
import time

import lightgbm as lgb
import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from core.config import load_config, repo_path
from model import baselines, villages
from model.ensemble import ModelC
from model.evaluate import cell_metrics, matched_recall, short_only, time_threshold
from model.features import check_columns, feature_columns, to_matrix

B_COLS = ("fire_id", "country", "t1", "kind", "hop", "gap_min", "label", "dist_active_m",
          "downwind_cos", "wind_speed_10m", "uphill_grade")


def fire_year(df: pd.DataFrame, cfg: dict) -> pd.Series:
    c = cfg["columns"]
    first = pd.to_datetime(df[c["t1"]], utc=True).groupby(df[c["fire_id"]]).transform("min")
    return first.dt.year


def fires_in(df: pd.DataFrame, cfg: dict, ev: dict) -> set:
    """Fire ids with a row inside the event's dates and bbox (same rule as the holdouts)."""
    c = cfg["columns"]
    t = pd.to_datetime(df[c["t1"]], utc=True)
    lon_min, lat_min, lon_max, lat_max = ev["bbox"]
    m = ((t >= pd.Timestamp(ev["start"], tz="UTC"))
         & (t < pd.Timestamp(ev["end"], tz="UTC") + pd.Timedelta(days=1))
         & df[c["lat"]].between(lat_min, lat_max) & df[c["lon"]].between(lon_min, lon_max))
    return set(df.loc[m, c["fire_id"]].unique())


def train_c(tr: pd.DataFrame, va: pd.DataFrame, raw: list[str], cfg: dict, n_seeds: int) -> ModelC:
    c, m = cfg["columns"], cfg["model"]["lgbm"]
    Xtr, Xva = to_matrix(tr, raw, cfg), to_matrix(va, raw, cfg)
    dtr = lgb.Dataset(Xtr, tr[c["label"]], weight=tr[c["weight"]], free_raw_data=False)
    dva = lgb.Dataset(Xva, va[c["label"]], weight=va[c["weight"]], reference=dtr)
    boosters = []
    for k in range(n_seeds):
        params = dict(m["params"], seed=cfg["model"]["seed"] + k)
        boosters.append(lgb.train(params, dtr, num_boost_round=m["num_boost_round"], valid_sets=[dva],
                                  callbacks=[lgb.early_stopping(m["early_stopping_rounds"], verbose=False)]))
    return ModelC(boosters, {"tag": "cv", "features": list(Xtr.columns), "raw_features": raw})


class CachedC:
    """C whose predictions are reused: villages.c_minutes asks the same rows for the same gaps once
    per threshold, and the sweep below scores several thresholds on the same event cells."""

    def __init__(self, model: ModelC):
        self.model, self.meta, self._cache = model, model.meta, {}

    def predict_rows(self, df: pd.DataFrame, cfg: dict) -> np.ndarray:
        c = cfg["columns"]
        key = (float(df[c["gap_min"]].iloc[0]), str(df[c["kind"]].iloc[0]), len(df), df.index[0], df.index[-1])
        if df[c["gap_min"]].nunique() != 1 or key not in self._cache:
            p = self.model.predict_rows(df, cfg)
            if df[c["gap_min"]].nunique() != 1:
                return p
            self._cache[key] = p
        return self._cache[key]


def village_sweep(vill: dict, recalls: list[float]) -> dict:
    """Villages pooled over the named events the fire reached, per C caution setting. 'C@' and 'B@' are
    the village-passes where C has a cell (like for like); 'C'/'B' are the whole 15 km area (C falls
    back to B beyond its cells)."""
    keys = ("villages_reached", "missed_villages", "missed_villages_judged", "missed_any_alert",
            "too_slow_at_last_pass_villages", "villages_told_leave_now", "false_alarm_villages")
    out = {}
    for r in recalls:
        tag = f"cv_{round(r * 1e4)}"
        for name, m in ((f"C@ {r}", f"C@C_{tag}"), (f"B@ (same cells as C@ {r})", f"B@C_{tag}"),
                        (f"C {r}", f"C_{tag}")):
            tot = {k: 0 for k in keys}
            for ev in vill.values():
                x = ev.get(m, {})
                for k in keys:
                    tot[k] += int(x.get(k) or 0)
            out[name] = tot
    tot = {k: sum(int(ev.get("B", {}).get(k) or 0) for ev in vill.values()) for k in keys}
    out["B"] = tot
    return out


def slice_metrics(d: pd.DataFrame, cfg: dict) -> dict:
    """d: pooled test rows with columns score_<m>, flag_<m> for each model."""
    out = {"n_fires": int(d[cfg["columns"]["fire_id"]].nunique())}
    models = [col[6:] for col in d.columns if col.startswith("score_")]
    for horizon, rows in (("1h", short_only(d, cfg)), ("all", d)):
        if not (rows[cfg["columns"]["label"]] == 1).any():
            continue
        out[horizon] = {"n_burned_cells": int((rows[cfg["columns"]["label"]] == 1).sum())}
        for m in models:
            cm = cell_metrics(rows, rows[f"flag_{m}"].to_numpy(), cfg)
            mr = matched_recall(rows, rows[f"score_{m}"].to_numpy(), cfg)
            out[horizon][m] = {"recall": cm["recall_1h"], "zone": cm["zone_cells_per_burned_cell"],
                               "zone95": mr.get("0.95", {}).get("zone_cells_per_burned_cell"),
                               "auc": mr.get("auc"),
                               # of the cells in the zone, the share that did NOT burn (= 1 - precision)
                               "zone_not_burned_pct": round(100 * (1 - cm["recall_1h"] / cm["zone_cells_per_burned_cell"]), 2)
                               if cm["zone_cells_per_burned_cell"] else None,
                               # of the cells that did not burn, the share inside the zone
                               "safe_cells_flagged_pct": round(100 * cm["false_alarm_cell_share"], 2)}
    return out


DIST_BANDS_KM = ((0, 1.5), (1.5, 3), (3, 6), (6, np.inf))


def by_distance(d: pd.DataFrame, cfg: dict) -> dict:
    """Where are the real burns and where is each zone? Bands of distance to the nearest active
    fire cell. If a band holds much zone but few burns, a shorter reach would cut false alarms there."""
    c = cfg["columns"]
    models = [col[5:] for col in d.columns if col.startswith("flag_")]
    out = {}
    for horizon, rows in (("1h", short_only(d, cfg)), ("all", d)):
        y = rows[c["label"]].to_numpy() == 1
        w = rows[c["weight"]].to_numpy(dtype=float)
        km = rows[c["dist_active"]].to_numpy(dtype=float) / 1000
        res = {}
        for lo, hi in DIST_BANDS_KM:
            b = (km >= lo) & (km < hi)
            band = {"burned_cells": int((y & b).sum()),
                    "share_of_all_burns_pct": round(100 * float((y & b).sum() / max(y.sum(), 1)), 1)}
            for m in models:
                f = rows[f"flag_{m}"].to_numpy()
                band[m] = {"share_of_zone_pct": round(100 * float((w * (f & b)).sum() / max((w * f).sum(), 1e-9)), 1),
                           "recall_in_band": round(float(f[y & b].mean()), 4) if (y & b).any() else None}
            res[f"{lo:g}-{hi:g} km"] = band
        out[horizon] = res
    return out


def crossval(cfg: dict) -> dict:
    c, cv = cfg["columns"], cfg["crossval"]
    path = repo_path(cfg["paths"]["train_table"])
    countries = cv["countries"]
    df = pd.read_parquet(path, filters=[(c["country"], "in", countries)])
    check_columns(df, cfg)
    raw = feature_columns(df, cfg)
    # other countries' rows: only what B's rate tuning needs (the full table does not fit in memory)
    cols = [col for col in B_COLS if col in pq.read_schema(path).names]
    other = short_only(pd.read_parquet(path, columns=cols, filters=[(c["country"], "not in", countries)]), cfg)
    other = other[other[c["label"]] == 1]

    df["cv_year"] = fire_year(df, cfg)
    years = sorted(df.cv_year.unique())
    rng = np.random.default_rng(cfg["model"]["seed"])
    pooled, fold_info, vill = [], [], {}
    for y in years:
        t0 = time.time()
        test = df[df.cv_year == y]
        rest = df[df.cv_year != y]
        fires = rest[c["fire_id"]].unique()
        val_ids = set(rng.choice(fires, size=max(1, int(len(fires) * cfg["model"]["val_fraction"])), replace=False))
        va, tr = rest[rest[c["fire_id"]].isin(val_ids)], rest[~rest[c["fire_id"]].isin(val_ids)]

        fit_dza = short_only(rest, cfg)
        rate_dza = baselines.tune_rate(fit_dza, "B", cfg)
        pos_all = pd.concat([fit_dza[fit_dza[c["label"]] == 1], other])
        rate_all = baselines.tune_rate(pos_all, "B", cfg)

        model = train_c(tr, va, raw, cfg, int(cv.get("n_seeds", 1)))
        thr = time_threshold(model, va[va[c["label"]] == 1], cfg)

        keep = [c["fire_id"], c["t1"], c["lat"], c["lon"], c["kind"], "hop", c["label"], c["weight"],
                c["dist_active"], c["gap_min"]]
        out = test[keep].copy()
        need = baselines.required_rate(test, "B", cfg)
        out["score_B_all"] = out["score_B_dza"] = -need
        out["flag_B_all"], out["flag_B_dza"] = need <= rate_all, need <= rate_dza
        p = model.predict_rows(test, cfg)
        out["score_C"], out["flag_C"] = p, p >= thr
        pooled.append(out)

        # villages: the named events of this year, scored by this fold's models (never saw year y)
        keys = {k for k, ev in cv.get("events", {}).items() if pd.Timestamp(ev["start"]).year == y}
        if keys:
            th = {"A": {"rate_m_per_min": baselines.tune_rate(pos_all, "A", cfg)},
                  "B": {"rate_m_per_min": rate_all}}
            recalls = cv["time_recalls"]   # C's caution, each threshold set on validation fires only
            cached, models = CachedC(model), {}
            for r, t in zip(recalls, time_threshold(model, va[va[c["label"]] == 1], cfg, recalls)):
                tag = f"cv_{round(r * 1e4)}"
                th[f"C_{tag}"], models[tag] = {"prob": t, "prob_time": t}, cached
            vill.update(villages.evaluate_villages(cfg, th, models, "events_replay", "events_dense", keys))
        fold_info.append({"year": int(y), "test_fires": int(test[c["fire_id"]].nunique()),
                          "train_fires": int(tr[c["fire_id"]].nunique()), "rate_B_all": round(rate_all, 1),
                          "rate_B_dza": round(rate_dza, 1), "c_threshold": thr,
                          "c_trees": [int(b.best_iteration) for b in model.boosters],
                          "seconds": round(time.time() - t0)})
        print(f"year {y}: {fold_info[-1]}", flush=True)

    d = pd.concat(pooled, ignore_index=True)
    report = {"generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
              "method": "leave-one-year-out on " + ",".join(countries) + " fires; predictions pooled",
              "folds": fold_info, "overall": slice_metrics(d, cfg), "by_distance": by_distance(d, cfg),
              "by_year": {}, "by_region": {}, "by_event": {}}
    # every test prediction, so later questions do not need a rerun
    d.to_parquet(repo_path("data/runs") / "crossval_pooled.parquet", index=False)
    yr = fire_year(d, cfg)
    for y in years:
        report["by_year"][str(y)] = slice_metrics(d[yr == y], cfg)
    for name, (lo, hi) in cv["regions"].items():
        report["by_region"][name] = slice_metrics(d[d[c["lon"]].between(lo, hi, inclusive="left")], cfg)
    for key, ev in cv.get("events", {}).items():
        ids = fires_in(d, cfg, ev)
        report["by_event"][key] = ({"name": ev["name"]} | slice_metrics(d[d[c["fire_id"]].isin(ids)], cfg)
                                   if ids else {"name": ev["name"], "status": "no fires matched: check bbox/dates"})
        report["by_event"][key]["villages"] = vill.get(key, {"status": "not measured: run data steps 6 and 7 --events"})
    report["village_sweep"] = village_sweep(vill, cv["time_recalls"])
    art = repo_path(cfg["paths"]["artifacts"])
    (art / "crossval.json").write_text(json.dumps(report, indent=2))
    return report


def main():
    r = crossval(load_config())
    print(json.dumps({k: r[k] for k in ("overall", "by_region")}, indent=2))


if __name__ == "__main__":
    main()
