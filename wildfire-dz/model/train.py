"""Train model C (LightGBM per cell). Holdout fires are never seen here.

  python -m model.train                    # mixed: every country in the table
  python -m model.train --countries DZA --tag dza   # Algeria-only, for the comparison
"""
from __future__ import annotations

import argparse
import json

import lightgbm as lgb

from core.config import load_config, repo_path
from model.features import feature_columns, load_table, split, to_matrix


def train(cfg: dict, countries: list[str] | None = None, tag: str = "mixed", table: str | None = None):
    df = load_table(cfg, table)
    tr, va, _ = split(df, cfg, countries)
    c = cfg["columns"]
    cols = feature_columns(df, cfg)
    Xtr, Xva = to_matrix(tr, cols, cfg), to_matrix(va, cols, cfg)
    dtr = lgb.Dataset(Xtr, tr[c["label"]], weight=tr[c["weight"]])
    dva = lgb.Dataset(Xva, va[c["label"]], weight=va[c["weight"]], reference=dtr)
    m = cfg["model"]["lgbm"]
    params = dict(m["params"], seed=cfg["model"]["seed"])
    booster = lgb.train(
        params, dtr, num_boost_round=m["num_boost_round"], valid_sets=[dva],
        callbacks=[lgb.early_stopping(m["early_stopping_rounds"], verbose=False)],
    )
    out = repo_path(cfg["paths"]["artifacts"])
    out.mkdir(parents=True, exist_ok=True)
    booster.save_model(str(out / f"model_c_{tag}.txt"))
    meta = {"tag": tag, "countries": countries or "all", "features": list(Xtr.columns),
            "n_train_rows": int(len(tr)), "n_val_rows": int(len(va)),
            "n_train_fires": int(tr[c["fire_id"]].nunique()), "n_val_fires": int(va[c["fire_id"]].nunique()),
            "best_iteration": int(booster.best_iteration or booster.current_iteration())}
    (out / f"features_{tag}.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))
    return booster, meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", nargs="*", default=None, help="e.g. DZA; default = all")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--table", default=None)
    a = ap.parse_args()
    tag = a.tag or ("mixed" if not a.countries else "_".join(a.countries).lower())
    train(load_config(), a.countries, tag, a.table)


if __name__ == "__main__":
    main()
