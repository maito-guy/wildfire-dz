"""Smoke test: train -> evaluate -> export on a tiny SYNTHETIC table (not real data)."""
import copy
import json

import numpy as np
import pandas as pd

from core.config import load_config
from model import baselines
from model.evaluate import evaluate
from model.export import export
from model.train import train


def synthetic_table(n_fires=40, rows=150, seed=0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    out = []
    for f in range(n_fires):
        held = f < 3  # first 3 fires sit inside the Kabylie 2021 holdout window/bbox
        t1 = pd.Timestamp("2021-08-10", tz="UTC") if held else pd.Timestamp("2019-07-01", tz="UTC")
        lat, lon = (36.6, 4.2) if held else (35.5, 1.0)
        d = rng.uniform(0, 3000, rows)
        cos = rng.uniform(-1, 1, rows)
        wind = rng.uniform(0, 50, rows)
        p = 1 / (1 + np.exp((d - 600 - 400 * cos) / 200))
        out.append(pd.DataFrame({
            "fire_id": f"F{f}", "country": "DZA" if f % 2 else "ESP", "t1": t1,
            "ix": 0, "iy": 0, "lat": lat, "lon": lon,
            "kind": np.where(rng.random(rows) < 0.8, "short", "long"),
            "dist_active_m": d, "dist_burned_m": d, "downwind_cos": cos, "uphill_grade": rng.normal(0, 0.1, rows),
            "gap_min": rng.uniform(20, 120, rows), "wind_speed_10m": wind, "slope": rng.uniform(0, 30, rows),
            "label": (rng.random(rows) < p).astype(int), "weight": 1.0,
        }))
    return pd.concat(out, ignore_index=True)


def make_cfg(tmp_path):
    cfg = copy.deepcopy(load_config())
    table = tmp_path / "train.parquet"
    synthetic_table().to_parquet(table)
    cfg["paths"]["train_table"] = str(table)
    cfg["paths"]["artifacts"] = str(tmp_path / "artifacts")
    cfg["model"]["lgbm"]["num_boost_round"] = 30
    return cfg


def test_train_evaluate_export(tmp_path):
    cfg = make_cfg(tmp_path)
    train(cfg, None, "mixed")
    train(cfg, ["DZA"], "dza")
    board = evaluate(cfg)
    assert board["fires"][0]["holdout"] == "kabylie_2021"
    models = board["fires"][0]["models"]
    assert {"A", "B", "C_mixed", "C_dza"} <= set(models)
    assert models["A"]["missed_villages"] is None  # not measured yet, never invented
    m = export(cfg, "mixed")
    assert m["model_c"]["tag"] == "mixed"
    assert json.loads((tmp_path / "artifacts" / "api_manifest.json").read_text())["rate_m_per_min"]["B"] > 0


def test_arrival_grid_shapes():
    cfg = load_config()
    g = baselines.arrival_grid(np.array([36.6, 36.601]), np.array([4.2, 4.2]), "B", 10.0, 45.0, 270.0, cfg)
    assert g["arrival"].shape == g["x"].shape
    assert g["embers_applied"] is True
    assert np.isfinite(g["arrival"]).all() and g["arrival"].min() == 0
