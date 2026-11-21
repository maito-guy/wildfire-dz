"""Tune thresholds on training fires, score A / B / C on whole held-out fires, write the scoreboard.

The ship rule is about false alarms at equal safety (SHIP_RULE): the officer reviews every zone,
so a model that flags less ground for the same share of burned cells saves them work.

  python -m model.evaluate            # uses every model_c_<tag>.txt found in artifacts/

Cell metrics on 1 h short pairs. Village metrics (missed villages, lead time, time error,
false-alarm villages) come from model/villages.py when replay_passes and places exist.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json

import numpy as np
import pandas as pd
from sklearn.metrics import average_precision_score, roc_auc_score

from core.config import load_config, repo_path
from model import baselines, ensemble, villages, wind
from model.features import load_table, split

WEATHER_NOTE = ("Training and evaluation weather is ERA5 reanalysis, i.e. a perfect forecast. "
                "Live accuracy will be lower.")
NOT_MEASURED = "not measured yet"


def cell_metrics(df: pd.DataFrame, flagged: np.ndarray, cfg: dict) -> dict:
    c = cfg["columns"]
    y = df[c["label"]].to_numpy() == 1
    w = df[c["weight"]].to_numpy(dtype=float)
    n_pos = int(y.sum())
    if n_pos == 0:
        return {"n_rows": int(len(df)), "n_burned_cells": 0, "recall_1h": None,
                "false_alarm_cell_share": None, "zone_cells_per_burned_cell": None}
    return {
        "n_rows": int(len(df)),
        "n_burned_cells": n_pos,
        "recall_1h": round(float(flagged[y].mean()), 4),
        "false_alarm_cell_share": round(float((w * (flagged & ~y)).sum() / max((w * ~y).sum(), 1e-9)), 4),
        "zone_cells_per_burned_cell": round(float((w * flagged).sum() / n_pos), 3),
    }


MATCHED_RECALLS = (0.90, 0.95)


def matched_recall(df: pd.DataFrame, score: np.ndarray, cfg: dict) -> dict:
    """Zone size and false alarms when each model's cut is set on THIS fire to catch exactly r of
    its burned cells. Uses the held-out labels to pick the cut, so it is a fair side-by-side
    comparison of ranking quality, not a deployable threshold."""
    y = df[cfg["columns"]["label"]].to_numpy() == 1
    if not y.any():
        return {}
    w = df[cfg["columns"]["weight"]].to_numpy(dtype=float)
    out = {"auc": round(float(roc_auc_score(y, score, sample_weight=w)), 4),
           "avg_precision": round(float(average_precision_score(y, score, sample_weight=w)), 4)}
    for r in MATCHED_RECALLS:
        cut = np.quantile(score[y], 1 - r)
        m = cell_metrics(df, score >= cut, cfg)
        out[f"{r:.2f}"] = {k: m[k] for k in ("recall_1h", "false_alarm_cell_share", "zone_cells_per_burned_cell")}
    return out


def village_metrics_placeholder() -> dict:
    return {"missed_villages": None, "median_lead_min": None, "false_alarm_villages": None,
            "status": NOT_MEASURED}


SHIP_RULE = ("The officer decides, so C must flag less ground than B for the same safety: on every "
             "holdout, C's zone is no larger than B's at 90 % and at 95 % of burned cells caught, and "
             "at its own threshold (set on training fires) C still catches >= 90 %; and on the villages "
             "where C has cells, it misses no more villages than B (missed_villages, C@ vs B@).")


def ship_decision(board: dict, boosters: dict) -> dict | str:
    """Per C tag: 'ship' if the rule holds on every holdout, else why not."""
    if not boosters:
        return NOT_MEASURED
    out = {}
    for tag in boosters:
        why = []
        for f in board["fires"]:
            mr, mod = f.get("matched_recall", {}), f.get("models", {})
            b, c = mr.get("B", {}), mr.get(f"C_{tag}", {})
            if not b or not c:
                why.append(f"{f['holdout']}: no rows")
                continue
            for r in ("0.90", "0.95"):
                if c[r]["zone_cells_per_burned_cell"] > b[r]["zone_cells_per_burned_cell"]:
                    why.append(f"{f['holdout']}: zone at {r} {c[r]['zone_cells_per_burned_cell']} > B "
                               f"{b[r]['zone_cells_per_burned_cell']}")
            lv = f.get("villages_where_c_has_cells", {})
            vb, vc = lv.get(f"B@C_{tag}", {}), lv.get(f"C@C_{tag}", {})
            if vc.get("missed_villages") is None or vb.get("missed_villages") is None:
                why.append(f"{f['holdout']}: villages not measured")
            elif vc["missed_villages"] > vb["missed_villages"]:
                why.append(f"{f['holdout']}: misses {vc['missed_villages']} villages, B misses {vb['missed_villages']}")
            rec = mod.get(f"C_{tag}", {}).get("recall_1h")
            if rec is None or rec < 0.90:
                why.append(f"{f['holdout']}: recall at threshold {rec} < 0.90")
        out[f"C_{tag}"] = "ship" if not why else "keep B: " + "; ".join(why)
    return out


def va_all_pos(df: pd.DataFrame, cfg: dict, countries) -> pd.DataFrame:
    """Burned cells of the validation fires, short AND long pairs (arrival times up to 16 h)."""
    _, va, _ = split(df, cfg, None if countries in (None, "all") else countries)
    return va[va[cfg["columns"]["label"]] == 1]


def time_threshold(model, pos: pd.DataFrame, cfg: dict, recall: float | list[float] | None = None):
    """Threshold for minutes-to-arrival (villages.c_minutes): C's predicted arrival must be no later
    than the real one for target_recall of the burned cells of the validation fires. A cell counts as
    on time if, at some step g <= its real gap, P(burning by g) >= threshold.
    recall: override safety.time_target_recall; a list returns one threshold per value."""
    c = cfg["columns"]
    gap = pos[c["gap_min"]].to_numpy(dtype=float)
    best = np.zeros(len(pos))
    lo, hi = cfg["model"].get("short_pair_min", [20, 120])
    for g in villages.C_GAPS:
        ok = (g <= gap) | (g == villages.C_GAPS[0])
        if not ok.any():
            continue
        kind = cfg["model"]["kind_for_1h"] if lo <= g <= hi else "long"
        p = model.predict_rows(pos.assign(**{c["gap_min"]: g, c["kind"]: kind}), cfg)
        best = np.where(ok, np.maximum(best, p), best)
    if isinstance(recall, list):
        return [float(np.quantile(best, 1 - r)) for r in recall]
    r = recall or cfg["safety"].get("time_target_recall", cfg["safety"]["target_recall"])
    return float(np.quantile(best, 1 - r))


class Blend:
    """C with wind and C without, averaged (model/wind.py). Scored like any other C."""

    def __init__(self, with_wind, no_wind, cfg):
        self.a, self.b, self.cfg = with_wind, no_wind, cfg
        self.meta = dict(with_wind.meta, tag=with_wind.meta["tag"] + "_blend")

    def predict_rows(self, df, cfg):
        return wind.blend(self.a, self.b, df, cfg)


def load_models(art, cfg) -> dict:
    """Every trained C, plus <tag>_blend wherever <tag> and <tag>_nowind both exist."""
    models = ensemble.load_all(art)
    for tag in list(models):
        if f"{tag}_nowind" in models:
            models[f"{tag}_blend"] = Blend(models[tag], models[f"{tag}_nowind"], cfg)
    return models


def robustness_metrics(df, score, flagged, cfg) -> dict:
    m = cell_metrics(df, flagged, cfg)
    mr = matched_recall(df, score, cfg)
    return {"recall_at_threshold": m["recall_1h"], "zone_at_threshold": m["zone_cells_per_burned_cell"],
            "auc": mr.get("auc"), "avg_precision": mr.get("avg_precision"),
            "zone90": mr.get("0.90", {}).get("zone_cells_per_burned_cell"),
            "zone95": mr.get("0.95", {}).get("zone_cells_per_burned_cell")}


def wind_robustness(hdf: pd.DataFrame, cfg: dict, thresholds: dict, models: dict) -> dict:
    """Every model scored with the real wind AND with a wrong 'forecast' wind (wind.forecast_like),
    averaged over a few random forecasts. Shows what an imperfect wind forecast costs each model."""
    if "bearing_deg" not in hdf or hdf.empty:
        return {"status": "needs bearing_deg: rebuild the table with data step 5"}
    seeds = cfg["wind_uncertainty"]["forecast_error"]["seeds"]
    runs: dict[str, list[dict]] = {}

    def add(name, d, score, flagged):
        runs.setdefault(name, []).append(robustness_metrics(d, score, flagged, cfg))

    for seed in seeds:
        noisy = wind.forecast_like(hdf, cfg, seed)
        for label, d in (("real wind", hdf), ("forecast wind", noisy)):
            need = baselines.required_rate(d, "B", cfg)
            add(f"B | {label}", d, -need, need <= thresholds["B"]["rate_m_per_min"])
            for tag, model in models.items():
                th = thresholds.get(f"C_{tag}")
                if th is None or (label == "real wind" and seed != seeds[0]):
                    continue
                cut = th.get("prob_time", th["prob"])
                p = model.predict_rows(d, cfg)
                add(f"C_{tag} | {label}", d, p, p >= cut)
                if label == "forecast wind" and not model.meta.get("no_wind") and "blend" not in tag:
                    e = wind.ensemble(model, d, cfg, cut)
                    add(f"C_{tag} wind scenarios | {label}", d, e["prob_mean"], e["prob_mean"] >= cut)
                    likely = e["agreement"] >= cfg["wind_uncertainty"]["likely_share"]
                    add(f"C_{tag} 'likely' zone | {label}", d, e["agreement"], likely)
                    add(f"C_{tag} 'possible' zone | {label}", d, e["prob_max"], e["agreement"] > 0)
    out = {}
    for name, rs in runs.items():
        out[name] = {k: (round(float(np.mean([r[k] for r in rs if r[k] is not None])), 4)
                         if any(r[k] is not None for r in rs) else None) for k in rs[0]}
    return out


def short_only(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """1 h cell metrics: short pairs to the very next pass (hop 1), as before multi-hop rows existed."""
    m = df[cfg["columns"]["kind"]] == cfg["model"]["kind_for_1h"]
    if "hop" in df:
        m &= df["hop"] == 1
    return df[m]


def evaluate(cfg: dict, table: str | None = None) -> dict:
    df = load_table(cfg, table)
    tr, va, holdouts = split(df, cfg)
    fit = short_only(pd.concat([tr, va]), cfg)
    if cfg["model"].get("baseline_countries"):       # B serves Algeria: optionally tune its rate there only
        fit = fit[fit[cfg["columns"]["country"]].isin(cfg["model"]["baseline_countries"])]
    art = repo_path(cfg["paths"]["artifacts"])
    art.mkdir(parents=True, exist_ok=True)

    thresholds: dict = {"target_recall": cfg["safety"]["target_recall"]}
    for m in ("A", "B"):
        thresholds[m] = {"rate_m_per_min": baselines.tune_rate(fit, m, cfg)}

    boosters = {}
    for tag, model in load_models(art, cfg).items():
        countries = model.meta.get("countries")
        _, va_tag, _ = split(df, cfg, None if countries in (None, "all") else countries)
        va_tag = short_only(va_tag, cfg)
        pos = va_tag[va_tag[cfg["columns"]["label"]] == 1]
        if pos.empty:
            continue
        p_pos = model.predict_rows(pos, cfg)
        thresholds[f"C_{tag}"] = {"prob": float(np.quantile(p_pos, 1 - cfg["safety"]["target_recall"])),
                                  "prob_time": time_threshold(model, va_all_pos(df, cfg, countries), cfg)}
        boosters[tag] = model

    vill = villages.evaluate_villages(cfg, thresholds, boosters)

    def village(key: str, m: str) -> dict:
        return vill.get(key, {}).get(m) or village_metrics_placeholder()

    board = {"generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
             "weather_note": WEATHER_NOTE, "horizon": "1h, pairs 20-120 min apart",
             "thresholds": thresholds, "fires": []}
    for key, hdf in holdouts.items():
        hdf = short_only(hdf, cfg)
        entry = {"holdout": key, "name": cfg["holdouts"][key]["name"],
                 "n_fires": int(hdf[cfg["columns"]["fire_id"]].nunique()), "models": {}}
        if hdf.empty:
            entry["status"] = "no rows matched this holdout: check bbox/dates in config.yaml"
        else:
            entry["matched_recall"] = {}
            for m in ("A", "B"):
                need = baselines.required_rate(hdf, m, cfg)
                flagged = need <= thresholds[m]["rate_m_per_min"]
                entry["models"][m] = cell_metrics(hdf, flagged, cfg) | village(key, m)
                entry["matched_recall"][m] = matched_recall(hdf, -need, cfg)  # lower rate needed = more at risk
            for tag, model in boosters.items():
                prob = model.predict_rows(hdf, cfg)
                th = thresholds[f"C_{tag}"]                   # the dashboard's 1 h zone = minutes <= 60,
                flagged = prob >= th.get("prob_time", th["prob"])   # so it uses the arrival threshold
                entry["models"][f"C_{tag}"] = cell_metrics(hdf, flagged, cfg) | village(key, f"C_{tag}")
                entry["matched_recall"][f"C_{tag}"] = matched_recall(hdf, prob, cfg)
            entry["wind_robustness"] = wind_robustness(hdf, cfg, thresholds, boosters)
            for m, res in vill.get(key, {}).items():
                if "@" in m:
                    entry.setdefault("villages_where_c_has_cells", {})[m] = res
        board["fires"].append(entry)

    board["ship_c"] = {"rule": SHIP_RULE, "decision": ship_decision(board, boosters)}
    (art / "thresholds.json").write_text(json.dumps(thresholds, indent=2))
    (art / "scoreboard.json").write_text(json.dumps(board, indent=2))
    print(json.dumps(board, indent=2))
    return board


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--table", default=None)
    evaluate(load_config(), ap.parse_args().table)


if __name__ == "__main__":
    main()
