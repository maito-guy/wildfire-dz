"""Village scoring on a tiny SYNTHETIC replay (not real data)."""
import pandas as pd

from core.config import load_config
from model import villages

T0 = pd.Timestamp("2021-08-10 00:00", tz="UTC")


def setup():
    # passes at 0, 50 and 100 min; the fire reaches village "near" at 100 min. "far" is never reached.
    rp = pd.DataFrame({"holdout": "kabylie_2021",
                       "t": [T0, T0 + pd.Timedelta("50min"), T0 + pd.Timedelta("100min")],
                       "lat": [36.60, 36.60, 36.65], "lon": [4.20, 4.20, 4.20]})
    places = pd.DataFrame({"id": ["near", "far"], "name": ["near", "far"],
                           "lat": [36.65, 36.70], "lon": [4.20, 4.30]})
    pl, _ = villages.truth(rp, places, load_config())
    pl["vid"] = range(len(pl))
    return pl


def test_truth_window():
    pl = setup().set_index("id")
    assert pl.loc["near", "t_first"] == T0 + pd.Timedelta("100min")
    assert pl.loc["near", "t_prev"] == T0 + pd.Timedelta("50min")
    assert pd.isna(pl.loc["far", "t_first"])


def test_too_slow_is_missed_and_fast_enough_is_not():
    cfg, pl = load_config(), setup()
    near = int(pl.set_index("id").loc["near", "vid"])
    far = int(pl.set_index("id").loc["far", "vid"])
    ts = [T0, T0 + pd.Timedelta("50min")]
    # at 50 min the fire is surely < 60 min away (seen there at 100 min)
    slow = pd.DataFrame({"vid": [near, near, far, far], "t": ts * 2, "minutes": [300, 90, 500, 500]})
    fast = pd.DataFrame({"vid": [near, near, far, far], "t": ts * 2, "minutes": [100, 40, 500, 30]})
    s, f = villages.score(slow, pl, cfg), villages.score(fast, pl, cfg)
    assert (s["villages_reached"], s["missed_villages"], s["missed_villages_judged"]) == (1, 1, 1)
    assert f["missed_villages"] == 0
    assert f["median_lead_min_range"] == [50.0, 100.0]       # "get ready" at 0 min, arrival in (50, 100]
    assert f["false_alarm_villages"] == 1                    # "far" told to leave, never reached
