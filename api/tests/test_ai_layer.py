"""Model C's advice on the replays (#52): `ai` on /predict, ai_minutes_left on villages and flags."""
import datetime as dt

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api import main
from core.config import load_config

T = dt.datetime(2021, 8, 9, 12, 5, tzinfo=dt.UTC)
LAT, LON = 36.65, 4.10


def fake_layer(path):
    """A block of C cells around the fire: likely within 60 min near it, possible within 50 min everywhere."""
    step = 375 / 110_574
    la, lo = np.meshgrid(np.arange(-40, 41) * step + LAT, np.arange(-40, 41) * step / np.cos(np.radians(LAT)) + LON)
    la, lo = la.ravel(), lo.ravel()
    near = np.hypot(la - LAT, lo - LON) < 0.02
    pd.DataFrame({"holdout": "kabylie_2021", "t": pd.Timestamp(T), "lat": la, "lon": lo,
                  "likely_min": np.where(near, 45.0, np.nan), "possible_min": 50.0}).to_parquet(path)
    path.with_suffix(".json").write_text('{"model": "C_dza", "likely_recall": 0.9, "possible_recall": 0.99}')


@pytest.fixture
def client(tmp_path, monkeypatch):
    cfg = load_config()
    fake = {**cfg, "paths": {**cfg["paths"], "replay_ai": str(tmp_path / "replay_ai.parquet")}}
    monkeypatch.setattr(main, "load_config", lambda: fake)
    c = TestClient(main.app)
    c.post("/reset")
    yield c, tmp_path
    c.post("/reset")


def predict(c, fire_id, time):
    return c.post("/predict", json={"fire_id": fire_id, "time": time.isoformat(), "model": "B",
                                    "wind": {"speed_kmh": 20, "from_deg": 270},
                                    "burning": [{"lat": LAT, "lon": LON}]}).json()


def test_no_file_means_no_ai(client):
    c, _ = client
    p = predict(c, "kabylie_2021", T)
    assert p["ai"] is None and p["model"] == "B" and p["zones"]["features"]   # B unchanged
    v = c.get("/villages/at-risk", params={"fire_id": "kabylie_2021"}).json()["villages"]
    assert v and all(x["ai_minutes_left"] is None for x in v)


def test_replay_pass_gets_c_zones_and_village_minutes(client):
    c, tmp = client
    fake_layer(tmp / "replay_ai.parquet")
    p = predict(c, "kabylie_2021", T + dt.timedelta(minutes=10))     # within ai_layer.match_min of the pass
    ai = p["ai"]
    assert ai["model"] == "C_dza" and ai["label"] and ai["time"].startswith("2021-08-09T12:05")
    kinds = {(f["properties"]["confidence"], f["properties"]["horizon_min"]) for f in ai["zones"]["features"]}
    assert kinds == {("likely", 60), ("likely", 120), ("possible", 60), ("possible", 120)}
    v = c.get("/villages/at-risk", params={"fire_id": "kabylie_2021"}).json()["villages"]
    got = [x["ai_minutes_left"] for x in v if x["ai_minutes_left"] is not None]
    assert got and set(got) == {50}                                     # C's possible-level minutes
    assert all(a["source"] == "ai_spread" for a in c.get("/alerts").json())   # C never makes flags itself
    vid = next(x["id"] for x in v if x["ai_minutes_left"] == 50)
    a = c.post("/alerts", json={"fire_id": "kabylie_2021", "village_id": vid, "level": "get_ready"}).json()
    assert a["ai_minutes_left"] == 50                                   # an alert carries C's view next to B's


def test_other_fire_or_time_gets_no_ai(client):
    c, tmp = client
    fake_layer(tmp / "replay_ai.parquet")
    assert predict(c, "kabylie_2021", T + dt.timedelta(hours=3))["ai"] is None
    assert predict(c, None, T)["ai"] is None                            # live fire: new id, no precomputed answer
