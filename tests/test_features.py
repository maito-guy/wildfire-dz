"""core/features.py (#18): the API builds model C's rows exactly as step 5 builds the training rows."""
import importlib.util
import sys
import time
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from core import features as F
from core.config import ROOT, load_config
from core.static_raster import LAYERS, StaticRaster

FIREDATA = ROOT / "data" / "firedata"
T0 = pd.Timestamp("2021-08-10 12:20", tz="UTC")


@pytest.fixture
def firedata(tmp_path, monkeypatch):
    """data/firedata's config.py and 05_build_table.py, writing nothing outside tmp_path."""
    monkeypatch.setenv("FIREDATA_DIR", str(tmp_path))
    monkeypatch.syspath_prepend(str(FIREDATA))
    for name in ("config", "05_build_table"):
        sys.modules.pop(name, None)
    spec = importlib.util.spec_from_file_location("05_build_table", FIREDATA / "05_build_table.py")
    b = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(b)
    yield b, sys.modules["config"]
    for name in ("config", "05_build_table"):
        sys.modules.pop(name, None)


def raster(lat0=36.3, lon0=4.0, n=200, seed=0) -> StaticRaster:
    rng = np.random.default_rng(seed)
    layers = {k: rng.random((n, n)).astype(np.float32) for k in LAYERS}
    layers["elev"] = (rng.random((n, n)) * 800).astype(np.float32)
    layers["aspect"] = (rng.random((n, n)) * 360).astype(np.float32)
    return StaticRaster(lat0=lat0, lon0=lon0, mlon=111_320 * np.cos(np.radians(lat0 + 0.3)), cell_m=375.0,
                        m_per_deg_lat=F.M_PER_DEG_LAT, layers=layers)


def detections(n_passes=3, per_pass=12, seed=1) -> pd.DataFrame:
    """A fire growing east, one NOAA-20 pass every 50 min, detections a few seconds apart."""
    rng = np.random.default_rng(seed)
    rows = []
    for k in range(n_passes):
        for j in range(per_pass):
            rows.append({"t": T0 + pd.Timedelta(minutes=50 * k, seconds=j), "sat": "NOAA20",
                         "lat": 36.60 + rng.normal(0, 0.004), "lon": 4.20 + 0.006 * k + rng.normal(0, 0.004),
                         "frp": float(rng.uniform(2, 40))})
    return pd.DataFrame(rows)


def hourly(hours=48) -> pd.DataFrame:
    t = pd.date_range(T0.floor("h") - pd.Timedelta(hours=42), periods=hours, freq="h")
    rng = np.random.default_rng(2)
    return pd.DataFrame({"time": t.strftime("%Y-%m-%dT%H:%M"),
                         "temperature_2m": rng.uniform(25, 40, hours), "relative_humidity_2m": rng.uniform(10, 50, hours),
                         "vapour_pressure_deficit": rng.uniform(1, 5, hours), "wind_speed_10m": rng.uniform(5, 40, hours),
                         "wind_direction_10m": rng.uniform(0, 360, hours), "wind_gusts_10m": rng.uniform(10, 60, hours),
                         "soil_moisture_0_to_7cm": rng.uniform(0.05, 0.2, hours),
                         "precipitation": np.where(np.arange(hours) == 3, 2.0, 0.0)})


def test_pipeline_constants_match_config(firedata):
    _, C = firedata
    f = load_config()["features"]
    assert (C.GRID_MARGIN_CELLS, C.CANDIDATE_RADIUS_CELLS, C.JITTER_CELLS, C.WEATHER_LOOKBACK_DAYS) == (
        f["grid_margin_cells"], f["candidate_radius_cells"], f["jitter_cells"], f["weather_lookback_days"])
    assert C.CELL_M == load_config()["grid"]["cell_m"]


def test_api_rows_equal_training_rows(firedata, monkeypatch):
    """Same fire, same pass: rows_from_detections (API) == 05's rows_for_pair keeping every cell (step 7)."""
    B, C = firedata
    monkeypatch.setattr(C, "NEG_KEEP", 1.0)
    monkeypatch.setattr(C, "NEG_KEEP_FAR", 1.0)
    cfg = load_config()
    det, r, w = detections(), raster(), hourly()
    grid = F.fire_grid(det.lat, det.lon, cfg["features"]["grid_margin_cells"])   # step 2: grid of the whole fire
    k = 1
    t_now = det[det.t < T0 + pd.Timedelta(minutes=50 * (k + 1))].t.max()
    api, _ = F.rows_from_detections(det, t_now, w, r, cfg, grid=grid)

    pidx, ptimes = F.assign_passes(det.t, det.sat)
    iy, ix = grid.index(det.lat, det.lon)
    cells = pd.DataFrame({"pass_idx": pidx, "ix": ix, "iy": iy, "frp": det.frp}).groupby(
        ["pass_idx", "ix", "iy"]).frp.sum().reset_index()
    cells = {j: c for j, c in cells.groupby("pass_idx")}
    t1 = ptimes.iloc[k]
    f = SimpleNamespace(lat0=grid.lat0, lon0=grid.lon0, mlon=grid.mlon, nx=grid.nx, ny=grid.ny,
                        lon_c=grid.lon_c, country="DZA")
    pr = SimpleNamespace(fire_id=1, pass_idx=k, t1=t1, kind="short", gap_min=50.0, sat1="NOAA20", sat2="NOAA20")
    wx = B.weather_at(F.prepare_weather(w, C.WEATHER_LOOKBACK_DAYS), t1)
    train = B.rows_for_pair(pr, f, cells, F.raster_terrain(r, grid), wx, np.random.default_rng(0))

    assert len(api) == len(train) > 50
    cols = [c for c in api.columns if c not in ("t1",)]
    key = ["iy", "ix"]
    a = api.sort_values(key).reset_index(drop=True)
    t = train.sort_values(key).reset_index(drop=True)
    pd.testing.assert_frame_equal(a[cols], t[cols], check_dtype=False)
    assert a.t1.iat[0] == t.t1.iat[0]
    assert set(t.columns) - set(a.columns) == {"fire_id", "country", "kind", "gap_min", "sat1", "sat2",
                                              "label", "hop", "weight"}


def test_rows_from_detections_uses_last_pass_and_is_fast():
    cfg = load_config()
    det = detections(n_passes=8, per_pass=60)
    t0 = time.perf_counter()
    rows, grid = F.rows_from_detections(det, det.t.max() + pd.Timedelta(minutes=5), hourly(60), raster(), cfg)
    assert time.perf_counter() - t0 < 3.0
    assert rows.pass_idx.unique().tolist() == [7]
    assert (rows.dist_burned_m > 375).all() and rows.dist_burned_m.max() <= 16 * 375
    assert rows[["elev", "fuel_tree", "temperature_2m", "wind_speed_2h"]].notna().all().all()
    assert rows.n_burned.iat[0] >= rows.n_active.iat[0] > 0


def test_rows_from_detections_errors():
    cfg = load_config()
    det = detections()
    with pytest.raises(ValueError, match="no detection"):
        F.rows_from_detections(det, T0 - pd.Timedelta(hours=1), hourly(), raster(), cfg)
    with pytest.raises(ValueError, match="no weather"):
        F.rows_from_detections(det, det.t.max(), hourly().iloc[:10], raster(), cfg)


def test_weather_at_vector_mean_and_rain():
    w = hourly()
    w.loc[:, "wind_direction_10m"] = [350.0, 10.0] * (len(w) // 2)
    w.loc[:, "wind_speed_10m"] = 20.0
    p = F.prepare_weather(w)
    t = p.index[10]
    wx = F.weather_at(p, t + pd.Timedelta(minutes=20))
    assert wx["wind_from_2h"] < 10 or wx["wind_from_2h"] > 350          # north, not 180
    assert wx["hours_since_rain"] == 7.0 and wx["rain_24h"] == 2.0
    assert F.weather_at(p, p.index[-1] + pd.Timedelta(hours=1)) is None


def test_assign_passes_splits_by_satellite_and_gap():
    t = pd.Series(pd.to_datetime(["2021-08-10 12:00", "2021-08-10 12:01", "2021-08-10 12:05",
                                  "2021-08-10 12:40", "2021-08-10 13:30"], utc=True))
    sat = pd.Series(["N20", "N20", "SNPP", "N20", "N20"])
    idx, times = F.assign_passes(t, sat)
    assert idx.tolist() == [0, 0, 1, 2, 3] and len(times) == 4
