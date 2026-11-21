"""Train model C (LightGBM per cell, averaged over model.n_seeds seeds). Holdout fires are never seen.

  python -m model.train                    # mixed: every country in the table
  python -m model.train --countries DZA --tag dza   # Algeria-only, for the comparison
"""
from __future__ import annotations

import argparse
import json

import lightgbm as lgb

from core.config import load_config, repo_path
from model.ensemble import ModelC
from model.features import feature_columns, load_table, split, to_matrix
from model.wind import WIND_FEATURES


def train(cfg: dict, countries: list[str] | None = None, tag: str = "mixed", table: str | None = None,
          no_wind: bool = False):
    df = load_table(cfg, table)
    tr, va, _ = split(df, cfg, countries)
    c = cfg["columns"]
    raw = feature_columns(df, cfg)
    Xtr, Xva = to_matrix(tr, raw, cfg), to_matrix(va, raw, cfg)
    if no_wind:                                        # the "wind unknown" model (model/wind.py)
        keep = [col for col in Xtr.columns if col not in WIND_FEATURES]
        Xtr, Xva = Xtr[keep], Xva[keep]
    dtr = lgb.Dataset(Xtr, tr[c["label"]], weight=tr[c["weight"]], free_raw_data=False)
    dva = lgb.Dataset(Xva, va[c["label"]], weight=va[c["weight"]], reference=dtr)
    m = cfg["model"]["lgbm"]
    out = repo_path(cfg["paths"]["artifacts"])
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob(f"model_c_{tag}*.txt"):
        old.unlink()
    boosters, files = [], []
    for k in range(int(cfg["model"].get("n_seeds", 1))):
        params = dict(m["params"], seed=cfg["model"]["seed"] + k)
        b = lgb.train(params, dtr, num_boost_round=m["num_boost_round"], valid_sets=[dva],
                      callbacks=[lgb.early_stopping(m["early_stopping_rounds"], verbose=False)])
        f = f"model_c_{tag}_s{k}.txt"
        b.save_model(str(out / f))
        boosters.append(b)
        files.append(f)
    gain = sum(b.feature_importance("gain") for b in boosters)
    top = sorted(zip(Xtr.columns, gain), key=lambda x: -x[1])[:10]
    meta = {"tag": tag, "countries": countries or "all", "no_wind": no_wind, "files": files,
            "raw_features": raw, "features": list(Xtr.columns),
            "n_train_rows": int(len(tr)), "n_val_rows": int(len(va)),
            "n_train_fires": int(tr[c["fire_id"]].nunique()), "n_val_fires": int(va[c["fire_id"]].nunique()),
            "train_countries": tr[c["country"]].value_counts().to_dict(),
            "best_iterations": [int(b.best_iteration or b.current_iteration()) for b in boosters],
            "top_features_by_gain": [[n, round(float(g / gain.sum()), 4)] for n, g in top]}
    (out / f"features_{tag}.json").write_text(json.dumps(meta, indent=2))
    print(json.dumps(meta, indent=2))
    return ModelC(boosters, meta), meta


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--countries", nargs="*", default=None, help="e.g. DZA; default = all")
    ap.add_argument("--tag", default=None)
    ap.add_argument("--table", default=None)
    ap.add_argument("--no-wind", action="store_true", help="drop every wind feature (tag gets _nowind)")
    a = ap.parse_args()
    tag = a.tag or ("mixed" if not a.countries else "_".join(a.countries).lower())
    if a.no_wind and not tag.endswith("_nowind"):
        tag += "_nowind"
    train(load_config(), a.countries, tag, a.table, a.no_wind)


if __name__ == "__main__":
    main()
