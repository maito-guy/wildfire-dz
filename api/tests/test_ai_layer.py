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
    fake = {**cfg, "paths": {**cfg["paths"], "replay_ai": str(tmp_path / "replay_ai.parquet")},
            "ai_layer": {**cfg["ai_layer"], "village_level": "possible"}}   # advice-mode tests: possible level
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


# ---- C ranks B's pending flags (#58) ---------------------------------------------------------------

def test_opinion_levels():
    from api.ai_layer import opinion
    assert opinion({"likely": 45, "possible": 30}, 120) == "likely"
    assert opinion({"likely": None, "possible": 120}, 120) == "possible"
    assert opinion({"likely": 150, "possible": 130}, 120) == "unlikely"     # C reaches it, but after 2 h
    assert opinion(None, 120) == "unlikely"                                # no C cell under the village


def pending(c):
    return c.get("/alerts", params={"status": "pending"}).json()


def predict_big(c):
    """A 5 x 5 cell fire in a strong wind: B flags about a dozen villages."""
    burning = [{"lat": LAT + i * 0.004, "lon": LON + j * 0.004} for i in range(-2, 3) for j in range(-2, 3)]
    r = c.post("/predict", json={"fire_id": "kabylie_2021", "time": T.isoformat(), "model": "B",
                                 "wind": {"speed_kmh": 60, "from_deg": 270}, "burning": burning})
    assert r.status_code == 200, r.text


def test_no_file_means_no_opinion_and_b_order(client):
    c, _ = client
    predict_big(c)
    v = c.get("/villages/at-risk", params={"fire_id": "kabylie_2021"}).json()["villages"]
    assert v and all(x["ai_opinion"] is None for x in v)
    flags = pending(c)
    assert flags and all(a["ai_opinion"] is None for a in flags)
    mins = [a["minutes_left"] for a in flags]
    assert mins == sorted(mins)                                           # B's minutes, as before


def test_c_ranks_b_flags_and_keeps_every_one(client):
    c, tmp = client
    predict_big(c)
    before = pending(c)
    assert len(before) >= 4
    c.post("/reset")
    # C's cells under B's flagged villages, in turn: likely, possible, C reaches it too late, no cell at all
    rows = []
    for i, a in enumerate(before):
        kind = i % 4
        if kind < 3:
            rows.append({"lat": a["area"]["lat"], "lon": a["area"]["lon"],
                         "likely_min": [30.0, np.nan, 200.0][kind], "possible_min": [20.0, 90.0, 180.0][kind]})
    pd.DataFrame(rows).assign(holdout="kabylie_2021", t=pd.Timestamp(T)).to_parquet(tmp / "replay_ai.parquet")
    predict_big(c)
    after = pending(c)
    assert {a["village_id"] for a in after} == {a["village_id"] for a in before}   # nothing dropped, nothing added
    want = {a["village_id"]: ["likely", "possible", "unlikely", "unlikely"][i % 4] for i, a in enumerate(before)}
    assert {a["village_id"]: a["ai_opinion"] for a in after} == want
    rank = {"likely": 0, "possible": 1, "unlikely": 2}
    keys = [(rank[a["ai_opinion"]], a["minutes_left"]) for a in after]
    assert keys == sorted(keys)                                           # opinion first, then B's minutes
    v = c.get("/villages/at-risk", params={"fire_id": "kabylie_2021"}).json()["villages"]
    assert all(x["ai_opinion"] in rank for x in v)                        # C answered: every village has an opinion
# ---------- display.model C (D-18): C's villages, times and flags replace B's when C has an answer ----------

@pytest.fixture
def client_c(tmp_path, monkeypatch):
    cfg = load_config()
    fake = {**cfg, "paths": {**cfg["paths"], "replay_ai": str(tmp_path / "replay_ai.parquet")},
            "display": {"model": "C"}, "ai_layer": {**cfg["ai_layer"], "village_level": "likely", "village_max_min": 120}}
    monkeypatch.setattr(main, "load_config", lambda: fake)
    c = TestClient(main.app)
    c.post("/reset")
    yield c, tmp_path
    c.post("/reset")


def predict_auto(c, fire_id, time):
    return c.post("/predict", json={"fire_id": fire_id, "time": time.isoformat(), "model": "auto",
                                    "wind": {"speed_kmh": 20, "from_deg": 270},
                                    "burning": [{"lat": LAT, "lon": LON}]}).json()


def test_display_c_replaces_b_villages_and_flags(client_c):
    c, tmp = client_c
    p0 = predict(c, "kabylie_2021", T)                              # explicit B: B's villages, no C file yet
    b_ids = {v["id"] for v in c.get("/villages/at-risk", params={"fire_id": "kabylie_2021"}).json()["villages"]}
    c.post("/reset")
    fake_layer(tmp / "replay_ai.parquet")
    p = predict_auto(c, "kabylie_2021", T)
    assert p0["model"] == "B" and p["model"] == "C" and p["fallback_reason"] is None and p["ai"]
    v = c.get("/villages/at-risk", params={"fire_id": "kabylie_2021"}).json()["villages"]
    assert v and {x["id"] for x in v} <= b_ids                      # only villages C reaches (likely, near the fire)
    assert all(x["model"] == "C" and x["minutes_left"] == x["ai_minutes_left"] == 45 for x in v)
    assert all(x["status"] == "leave_now" and "b_minutes_left" in x for x in v)
    flags = c.get("/alerts", params={"status": "pending"}).json()
    assert flags and all(a["model"] == "C" and a["minutes_left"] == 45 for a in flags)
    assert {a["village_id"] for a in flags} == {x["id"] for x in v}


def test_display_c_falls_back_to_b_without_an_answer(client_c):
    c, tmp = client_c
    fake_layer(tmp / "replay_ai.parquet")
    p = predict_auto(c, "fire_live_1", T)                           # not a replay: C has no answer
    assert p["model"] == "B" and "model C has no answer" in p["fallback_reason"] and p["ai"] is None
    v = c.get("/villages/at-risk", params={"fire_id": "fire_live_1"}).json()["villages"]
    assert all(x["model"] == "B" for x in v)


def test_display_c_drops_villages_beyond_two_hours(client_c):
    c, tmp = client_c
    fake_layer(tmp / "replay_ai.parquet")
    d = pd.read_parquet(tmp / "replay_ai.parquet")
    d["likely_min"] = np.where(d.likely_min.notna(), 180.0, np.nan)   # C: likely only after 3 h
    d.to_parquet(tmp / "replay_ai.parquet")
    predict_auto(c, "kabylie_2021", T)
    assert c.get("/villages/at-risk", params={"fire_id": "kabylie_2021"}).json()["villages"] == []
    assert c.get("/alerts", params={"status": "pending"}).json() == []
