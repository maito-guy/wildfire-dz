"""Model C on disk: a few LightGBM boosters (one per seed) whose probabilities are averaged.

features_<tag>.json lists the files ("files"), the raw table columns ("raw_features") and the
matrix columns in order ("features"). Averaging seeds makes the zone steadier on small holdouts.
"""
from __future__ import annotations

import json
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd

from model.features import to_matrix


class ModelC:
    def __init__(self, boosters: list[lgb.Booster], meta: dict):
        self.boosters, self.meta = boosters, meta
        self.features = meta["features"]
        self.raw = meta.get("raw_features") or [f for f in self.features if f != "is_short"]

    def predict_rows(self, df: pd.DataFrame, cfg: dict) -> np.ndarray:
        """P(cell burning by the next pass, gap_min minutes later) for table-shaped rows."""
        X = to_matrix(df, self.raw, cfg)[self.features]
        return np.mean([b.predict(X) for b in self.boosters], axis=0)


def load(art: Path, tag: str) -> ModelC:
    meta = json.loads((art / f"features_{tag}.json").read_text())
    files = meta.get("files") or [f"model_c_{tag}.txt"]
    return ModelC([lgb.Booster(model_file=str(art / f)) for f in files], meta)


def load_all(art: Path) -> dict[str, ModelC]:
    out = {}
    for p in sorted(art.glob("features_*.json")):
        tag = p.stem.removeprefix("features_")
        try:
            out[tag] = load(art, tag)
        except (lgb.basic.LightGBMError, FileNotFoundError, KeyError):
            continue
    return out
