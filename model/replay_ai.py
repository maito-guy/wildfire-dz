"""Model C as advice on the replays: spread zones and arrival times for every pass of the holdout fires (#52).

B stays the model of record: it creates every pending flag. C is shown next to it so the operator can judge
those flags; cross-validation (model/crossval.py) found C's map much sharper than B's but not safe enough to
decide alone which villages to warn.

For every holdout pass and every cell around the fire (data step 7, holdout_dense.parquet), with the real wind:
  likely_min    first g in villages.C_GAPS where P(burning within g) >= the "likely" threshold
  possible_min  the same with the "possible" threshold (lower, so never later than likely_min)
Each threshold is set on C's validation fires so that C's zone catches ai_layer.likely_recall (0.90) or
possible_recall (0.99) of the cells that really burned. On Kabylie 2021 (1 h): likely catches 93 % of burns while
flagging 15 % of the cells around the fire, possible 98 % / 46 %, B 98 % / 64 %. C is advice, so it does not use
the cautious crossval setting (0.9995 flagged 79 % there). C is ai_layer.model_tag, trained without the holdout
fires, so the replay is a fair test.

  python -m model.replay_ai      # -> paths.replay_ai (+ the same name .json with the model and threshold)
"""
from __future__ import annotations

import datetime as dt
import json

import numpy as np
import pandas as pd

from core.config import load_config, repo_path
from model import ensemble, villages
from model.evaluate import time_threshold, va_all_pos


def thresholds(model, cfg: dict) -> dict[str, float]:
    """C's time thresholds for the likely and possible zones, from the validation fires of the model's split."""
    c = cfg["columns"]
    countries = model.meta.get("countries")
    countries = None if countries in (None, "all") else countries
    path = repo_path(cfg["paths"]["train_table"])
    df = pd.read_parquet(path, filters=[(c["country"], "in", countries)] if countries else None)
    ai = cfg["ai_layer"]
    likely, possible = time_threshold(model, va_all_pos(df, cfg, countries), cfg,
                                      recall=[float(ai["likely_recall"]), float(ai["possible_recall"])])
    return {"likely": likely, "possible": possible}


def first_minutes(model, rows: pd.DataFrame, thr: dict[str, float], cfg: dict) -> dict[str, np.ndarray]:
    """Per threshold, the first g in C_GAPS where P(burning within g) >= it (inf if never). One prediction
    per g serves every threshold; first crossing as in villages.c_minutes."""
    c = cfg["columns"]
    lo, hi = cfg["model"].get("short_pair_min", [20, 120])
    first = {k: np.full(len(rows), np.inf) for k in thr}
    for g in villages.C_GAPS:
        kind = cfg["model"]["kind_for_1h"] if lo <= g <= hi else "long"
        p = model.predict_rows(rows.assign(**{c["gap_min"]: g, c["kind"]: kind}), cfg)
        for k, t in thr.items():
            first[k] = np.where(np.isinf(first[k]) & (p >= t), g, first[k])
    return first


def zone_rows(model, dense: pd.DataFrame, thr: dict[str, float], cfg: dict) -> pd.DataFrame:
    """One row per (holdout, pass time, cell) that C reaches within 120 min at the possible level."""
    c = cfg["columns"]
    # step 7 repeats each cell once per later pass it is paired with; the features C uses are the same
    dense = dense.drop_duplicates(["holdout", c["fire_id"], c["t1"], "ix", "iy"]).reset_index(drop=True)
    first = first_minutes(model, dense, thr, cfg)
    out = pd.DataFrame({"holdout": dense["holdout"].to_numpy(),
                        "t": pd.to_datetime(dense[c["t1"]], utc=True).to_numpy(),
                        "lat": dense[c["lat"]].round(5).to_numpy(), "lon": dense[c["lon"]].round(5).to_numpy(),
                        "likely_min": first["likely"], "possible_min": first["possible"]})
    out = out[out.possible_min <= 120]
    # several fires of one holdout can share a cell: keep the most urgent answer
    out = out.groupby(["holdout", "t", "lat", "lon"], as_index=False).agg(
        likely_min=("likely_min", "min"), possible_min=("possible_min", "min"))
    out["likely_min"] = out.likely_min.where(np.isfinite(out.likely_min))   # not likely at all -> NaN
    return out


def build(cfg: dict) -> dict:
    ai = cfg["ai_layer"]
    art = repo_path(cfg["paths"]["artifacts"])
    model = ensemble.load(art, ai["model_tag"])
    thr = thresholds(model, cfg)
    dense = pd.read_parquet(repo_path(cfg["paths"]["holdout_dense"]))
    rows = zone_rows(model, dense, thr, cfg)
    out = repo_path(cfg["paths"]["replay_ai"])
    rows.to_parquet(out, index=False)
    meta = {"generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"), "model": f"C_{ai['model_tag']}",
            "likely_recall": float(ai["likely_recall"]), "possible_recall": float(ai["possible_recall"]),
            "thresholds": thr, "n_rows": int(len(rows)),
            "passes": {k: int(g.t.nunique()) for k, g in rows.groupby("holdout")}}
    out.with_suffix(".json").write_text(json.dumps(meta, indent=2))
    return meta


def main():
    print(json.dumps(build(load_config()), indent=2))


if __name__ == "__main__":
    main()
