"""model/wind.py on tiny SYNTHETIC rows (not real data)."""
import numpy as np
import pandas as pd

from core.config import load_config
from model import wind


def rows():
    # wind from the west (270) blows toward the east (90); cell 0 is east of the fire, cell 1 west
    return pd.DataFrame({"fire_id": [1, 1, 2], "pass_idx": [0, 0, 0], "bearing_deg": [90.0, 270.0, 0.0],
                         "wind_from_2h": 270.0, "wind_dir_now": 270.0, "wind_speed_2h": 20.0,
                         "wind_speed_10m": 20.0, "wind_gusts_10m": 30.0, "gust_max_2h": 30.0,
                         "downwind_cos": [1.0, -1.0, 0.0]})


def test_rotating_the_wind_recomputes_downwind():
    cfg = load_config()
    same = wind.with_wind(rows(), cfg, 0, 1.0)
    assert np.allclose(same.downwind_cos, [1, -1, 0], atol=1e-9)
    flipped = wind.with_wind(rows(), cfg, 180, 2.0)
    assert np.allclose(flipped.downwind_cos, [-1, 1, 0], atol=1e-9)
    assert (flipped.wind_speed_2h == 40).all() and (flipped.wind_from_2h == 90).all()


def test_forecast_error_is_shared_by_one_pass():
    noisy = wind.forecast_like(rows(), load_config(), seed=1)
    assert noisy.wind_from_2h.iat[0] == noisy.wind_from_2h.iat[1]        # same fire, same pass
    assert noisy.wind_from_2h.iat[0] != noisy.wind_from_2h.iat[2]        # another fire


def test_scenarios_cover_the_grid():
    cfg = load_config()
    w = cfg["wind_uncertainty"]
    assert len(wind.scenarios(cfg)) == len(w["dir_offsets_deg"]) * len(w["speed_factors"])
