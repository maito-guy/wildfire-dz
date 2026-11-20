"""Tune thresholds on training fires, score A / B / C on whole held-out fires, write the scoreboard.

  python -m model.evaluate            # uses every model_c_<tag>.txt found in artifacts/

Cell metrics only for now (1 h, short pairs). Village metrics (missed villages, lead time,
false-alarm villages) need the replay evaluator and stay null = "not measured yet".
"""
from __future__ import annotations

import argparse
import datetime as dt
import json

import lightgbm as lgb
import numpy as np
import pandas as pd

from core.config import load_config, repo_path
from model import baselines
from model.features import load_table, split, to_matrix

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


def village_metrics_placeholder() -> dict:
    return {"missed_villages": None, "median_lead_min": None, "false_alarm_villages": None,
            "status": NOT_MEASURED}


def short_only(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    return df[df[cfg["columns"]["kind"]] == cfg["model"]["kind_for_1h"]]


def evaluate(cfg: dict, table: str | None = None) -> dict:
    df = load_table(cfg, table)
    tr, va, holdouts = split(df, cfg)
    fit = short_only(pd.concat([tr, va]), cfg)
    art = repo_path(cfg["paths"]["artifacts"])
    art.mkdir(parents=True, exist_ok=True)

    thresholds: dict = {"target_recall": cfg["safety"]["target_recall"]}
    for m in ("A", "B"):
        thresholds[m] = {"rate_m_per_min": baselines.tune_rate(fit, m, cfg)}

    boosters = {}
    for p in sorted(art.glob("model_c_*.txt")):
        tag = p.stem.removeprefix("model_c_")
        b = lgb.Booster(model_file=str(p))
        feats = json.loads((art / f"features_{tag}.json").read_text())["features"]
        _, va_tag, _ = split(df, cfg, None if tag == "mixed" else [s.upper() for s in tag.split("_")])
        va_tag = short_only(va_tag, cfg)
        pos = va_tag[va_tag[cfg["columns"]["label"]] == 1]
        if pos.empty:
            continue
        p_pos = b.predict(to_matrix(pos, [f for f in feats if f != "is_short"], cfg)[feats])
        thresholds[f"C_{tag}"] = {"prob": float(np.quantile(p_pos, 1 - cfg["safety"]["target_recall"]))}
        boosters[tag] = (b, feats)

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
            for m in ("A", "B"):
                flagged = baselines.required_rate(hdf, m, cfg) <= thresholds[m]["rate_m_per_min"]
                entry["models"][m] = cell_metrics(hdf, flagged, cfg) | village_metrics_placeholder()
            for tag, (b, feats) in boosters.items():
                prob = b.predict(to_matrix(hdf, [f for f in feats if f != "is_short"], cfg)[feats])
                flagged = prob >= thresholds[f"C_{tag}"]["prob"]
                entry["models"][f"C_{tag}"] = cell_metrics(hdf, flagged, cfg) | village_metrics_placeholder()
        board["fires"].append(entry)

    board["ship_c"] = {"rule": "C ships only if it beats B on missed villages and lead time",
                       "decision": NOT_MEASURED}
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
