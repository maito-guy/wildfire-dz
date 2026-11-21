"""model/replay_ai.py with a fake C: first crossing per level, dedupe of step 7 rows, 2 h cut."""
import numpy as np
import pandas as pd

from core.config import load_config
from model import replay_ai


class RisingC:
    """P(burning within g) = g / 1000 * (cell's own factor), so the first crossing is easy to predict."""
    meta = {"countries": ["DZA"]}

    def predict_rows(self, df, cfg):
        return df["gap_min"].to_numpy(dtype=float) / 1000 * df["factor"].to_numpy(dtype=float)


def test_zone_rows_levels_and_cut():
    cfg = load_config()
    t = pd.Timestamp("2021-08-09T12:05Z")
    dense = pd.DataFrame({"holdout": "kabylie_2021", "fire_id": [1, 1, 1, 1], "t1": t, "ix": [0, 0, 1, 2],
                          "iy": [0, 0, 0, 0], "lat": [36.6, 36.6, 36.61, 36.62], "lon": 4.1,
                          "gap_min": [50, 300, 50, 50], "kind": "short", "factor": [1.0, 1.0, 0.5, 0.01]})
    out = replay_ai.zone_rows(RisingC(), dense, {"likely": 0.06, "possible": 0.03}, cfg)
    out = out.sort_values("lat").reset_index(drop=True)
    assert len(out) == 2                                    # cell (0,0) once; cell (2,0) never within 120 min
    assert out.loc[0, "likely_min"] == 60 and out.loc[0, "possible_min"] == 30
    assert out.loc[1, "likely_min"] == 120 and out.loc[1, "possible_min"] == 60
    assert (out.possible_min <= out.likely_min).all()
    assert np.isnan(replay_ai.zone_rows(RisingC(), dense.assign(factor=0.3), {"likely": 0.3, "possible": 0.03},
                                        cfg).likely_min).all()   # possible but never likely -> NaN
