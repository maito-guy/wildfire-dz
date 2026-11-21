"""Model C in /predict (#20): loads the exported artifacts, beats nothing to B, falls back to B with a reason.

A tiny LightGBM booster is trained here on rows from core.features.rows_from_detections and written in the
format of model/train.py + model/export.py, so no Drive file is needed. Weather is faked (C-10)."""
import json
import time

import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api import predictor
from api.main import app
from core import features as F
from core.config import load_config
from core.static_raster import LAYERS, META
from model.ensemble import ModelC
from model.features import feature_columns, to_matrix
from model.villages import C_GAPS

T0 = pd.Timestamp("2021-08-10 12:20", tz="UTC")
FIRE = [{"lat": 36.60 + 0.004 * i, "lon": 4.20 + 0.004 * j} for i in range(3) for j in range(3)]
LAT0, LON0, N = 36.3, 4.0, 200
REAL_HOURLY = predictor.hourly_weather


def hourly(hours=60) -> pd.DataFrame:
    t = pd.date_range(T0.floor("h") - pd.Timedelta(hours=48), periods=hours, freq="h")
    rng = np.random.default_rng(2)
    return pd.DataFrame({"time": t.strftime("%Y-%m-%dT%H:%M"),
                         "temperature_2m": rng.uniform(25, 40, hours), "relative_humidity_2m": rng.uniform(10, 50, hours),
                         "vapour_pressure_deficit": rng.uniform(1, 5, hours), "wind_speed_10m": rng.uniform(5, 40, hours),
                         "wind_direction_10m": rng.uniform(0, 360, hours), "wind_gusts_10m": rng.uniform(10, 60, hours),
                         "soil_moisture_0_to_7cm": rng.uniform(0.05, 0.2, hours),
                         "precipitation": np.where(np.arange(hours) == 3, 2.0, 0.0)})


def write_raster(path):
    rng = np.random.default_rng(0)
    layers = {k: rng.random((N, N)).astype(np.float32) for k in LAYERS}
    layers["elev"] = (rng.random((N, N)) * 800).astype(np.float32)
    layers["aspect"] = (rng.random((N, N)) * 360).astype(np.float32)
    meta = {"lat0": LAT0, "lon0": LON0, "mlon": 111_320 * np.cos(np.radians(LAT0 + 0.3)), "cell_m": 375.0,
            "m_per_deg_lat": F.M_PER_DEG_LAT}
    assert set(meta) == set(META)
    np.savez(path, **layers, **meta)


def write_artifacts(art, cfg, raster_path):
    """A one-seed C in model/train.py's format, exported like model/export.py (tag "t")."""
    from core.static_raster import load

    det = pd.DataFrame({"t": T0, "sat": "NOAA20", "lat": [p["lat"] for p in FIRE], "lon": [p["lon"] for p in FIRE],
                        "frp": 10.0})
    rows, _ = F.rows_from_detections(det, T0, hourly(), load(raster_path), cfg)
    c = cfg["columns"]
    df = pd.concat([rows.assign(**{c["gap_min"]: g, c["kind"]: "short" if g <= 120 else "long"})
                    for g in (20, 60, 120, 240)], ignore_index=True)
    df["label"] = (df[c["dist_active"]] <= 25.0 * df[c["gap_min"]]).astype(int)   # reached at 25 m/min
    raw = feature_columns(df, cfg)
    X = to_matrix(df, raw, cfg)
    b = lgb.train({"objective": "binary", "num_leaves": 7, "min_data_in_leaf": 5, "verbose": -1},
                  lgb.Dataset(X, df["label"]), num_boost_round=30)
    art.mkdir(parents=True, exist_ok=True)
    b.save_model(str(art / "model_c_t_s0.txt"))
    (art / "features.json").write_text(json.dumps({"tag": "t", "files": ["model_c_t_s0.txt"],
                                                   "raw_features": raw, "features": list(X.columns)}))
    (art / "thresholds.json").write_text(json.dumps({"B": {"rate_m_per_min": 10.0},
                                                     "C_t": {"prob": 0.3, "prob_time": 0.5}}))
    (art / "api_manifest.json").write_text(json.dumps({
        "rate_m_per_min": {"A": 15.0, "B": 10.0},
        "model_c": {"tag": "t", "features": "features.json", "files": ["model_c_t_s0.txt"], "prob_threshold": 0.3}}))


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    d = tmp_path_factory.mktemp("c")
    write_raster(d / "static.npz")
    write_artifacts(d / "artifacts", load_config(), d / "static.npz")
    return d


@pytest.fixture
def cfg(built, monkeypatch):
    """The app's own config pointed at the tmp artifacts and raster; weather faked."""
    c = load_config()
    monkeypatch.setitem(c["paths"], "artifacts", str(built / "artifacts"))
    monkeypatch.setitem(c["paths"], "static_raster", str(built / "static.npz"))
    monkeypatch.setattr(predictor, "hourly_weather", lambda lat, lon, t, cfg: hourly())
    return c


def run(cfg, model="C"):
    lat = np.array([p["lat"] for p in FIRE])
    lon = np.array([p["lon"] for p in FIRE])
    return predictor.run_model(model, lat, lon, 20.0, 270.0, cfg, time=T0.to_pydatetime())


def test_c_runs_and_changes_the_grid(cfg):
    t = time.perf_counter()
    model, reason, grid = run(cfg)
    assert time.perf_counter() - t < 10
    assert (model, reason) == ("C", None)
    _, _, b = run(cfg, "B")
    assert grid["arrival"].shape == b["arrival"].shape
    assert (grid["arrival"] != b["arrival"]).any()            # C's cells replaced B's near the fire
    assert (grid["arrival"][b["arrival"] == 0] == 0).all()    # burning cells stay burning
    far = np.hypot(grid["x"], grid["y"]) > 10_000
    assert np.array_equal(grid["arrival"][far], b["arrival"][far])   # beyond C's 6 km, B
    changed = grid["arrival"][grid["arrival"] != b["arrival"]]
    assert set(np.unique(changed)) <= {*C_GAPS, np.inf}          # C's answers are its gap steps
    assert (changed <= 120).any()                                   # and some cells are in its 2 h zone
    assert run(cfg, "auto")[0] == "C"                         # auto picks C when exported


def test_raising_model_falls_back_to_b(cfg, monkeypatch):
    def boom(self, df, cfg):
        raise RuntimeError("bad booster")
    monkeypatch.setattr(ModelC, "predict_rows", boom)
    model, reason, grid = run(cfg)
    assert model == "B" and "RuntimeError" in reason and "bad booster" in reason
    assert grid["arrival"].size


def test_timeout_falls_back_to_b(cfg, monkeypatch):
    monkeypatch.setitem(cfg["api"], "predict_timeout_s", 0.2)
    monkeypatch.setattr(predictor, "hourly_weather", lambda *a: time.sleep(1.5) or hourly())
    t = time.perf_counter()
    model, reason, _ = run(cfg)
    assert time.perf_counter() - t < 1.0
    assert model == "B" and "longer than 0.2 s" in reason


def test_offline_weather_falls_back_to_b(cfg, monkeypatch):
    monkeypatch.setattr(predictor, "hourly_weather", REAL_HOURLY)   # conftest's offline client answers
    predictor._wx_cache.clear()
    model, reason, _ = run(cfg)
    assert model == "B" and "no weather" in reason


def test_missing_files_fall_back_and_health(cfg, built, tmp_path, monkeypatch):
    client = TestClient(app)
    assert client.get("/health").json()["model_c_exported"] is True
    assert predictor.model_c_status(cfg) == (True, None)

    art = tmp_path / "art"
    art.mkdir()
    for f in ("features.json", "thresholds.json", "api_manifest.json"):   # model_c_t_s0.txt "deleted"
        (art / f).write_text((built / "artifacts" / f).read_text())
    monkeypatch.setitem(cfg["paths"], "artifacts", str(art))
    model, reason, _ = run(cfg)
    assert model == "B" and "model_c_t_s0.txt" in reason
    assert client.get("/health").json()["model_c_exported"] is False

    monkeypatch.setitem(cfg["paths"], "static_raster", str(tmp_path / "none.npz"))
    monkeypatch.setitem(cfg["paths"], "artifacts", str(built / "artifacts"))
    assert "static raster missing" in run(cfg)[1]


def test_not_exported(cfg, tmp_path, monkeypatch):
    monkeypatch.setitem(cfg["paths"], "artifacts", str(tmp_path))
    assert run(cfg, "auto")[:2] == ("B", None)                # nothing exported: B is expected, no reason
    model, reason, _ = run(cfg, "C")
    assert model == "B" and "not exported" in reason


def test_predict_endpoint_reports_c(cfg):
    r = TestClient(app).post("/predict", json={"burning": FIRE, "time": T0.isoformat(), "model": "C",
                                               "wind": {"speed_kmh": 20, "from_deg": 270}})
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "C" and body["fallback_reason"] is None and body["cells"]
