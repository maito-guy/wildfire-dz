"""Today's risk layer and preventive flags (#28): stub fallback, file contract, one flag per place and day."""
import copy
import json

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api import impact, risk
from api.alerts import store
from api.main import app
from core.config import load_config

TOKEN = "test-token"
client = TestClient(app, headers={"X-Operator-Token": TOKEN})


@pytest.fixture
def cfg(monkeypatch, tmp_path):
    """A config whose risk file lives in tmp_path (missing until a test writes it), and no places file."""
    c = copy.deepcopy(load_config())
    c["paths"]["risk_today"] = str(tmp_path / "risk_today.parquet")
    monkeypatch.setattr(risk, "load_config", lambda: c)
    monkeypatch.setattr(impact, "real_places", lambda: None)
    monkeypatch.setenv("OPERATOR_TOKEN", TOKEN)
    assert client.post("/reset").status_code == 200
    yield c
    store.reset()


def write_risk(c: dict, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_parquet(c["paths"]["risk_today"])


def row(lat, lon, score, level, factors="wind; dryness", date="2026-11-20"):
    return {"date": date, "lat": lat, "lon": lon, "score": score, "level": level, "top_factors": factors}


def pending():
    return client.get("/alerts", params={"status": "pending"}).json()


# ---- stub ------------------------------------------------------------------------------------

def test_stub_when_file_missing(cfg):
    r = client.get("/risk")
    assert r.status_code == 200
    j = r.json()
    assert j["stub"] is True and j["generated_at"] is None
    assert j["cells"] and all(c["lat"] >= cfg["scope"]["lat_min"] for c in j["cells"])
    assert {c["level"] for c in j["cells"]} <= {"moderate", "high", "very_high"}  # low is not sent
    assert any(c["level"] == "very_high" for c in j["cells"])
    assert 0 < len(j["places"]) <= cfg["risk"]["max_flags"]
    assert all(p["name"].startswith("STUB") and p["top_factors"] for p in j["places"])


def test_stub_is_deterministic(cfg):
    a = risk.stub_cells(cfg, "2026-11-20")
    b = risk.stub_cells(cfg, "2026-11-20")
    pd.testing.assert_frame_equal(a, b)


# ---- real file -------------------------------------------------------------------------------

def test_real_file_latest_date_simplified(cfg):
    d = cfg["risk"]["display_cell_deg"]
    write_risk(cfg, [
        row(36.601, 4.101, 0.95, "very_high", ["wind", "past fires"]),
        row(36.602, 4.102, 0.40, "moderate", ["heat"]),          # same display cell: the higher score wins
        row(36.0, 2.0, 0.10, "low", []),                   # below min_level_shown: not sent
        row(35.5, 1.0, 0.6, "high", ["heat"]),
        row(36.8, 5.9, 0.99, "very_high", ["wind"], date="2026-11-19"),  # older day: ignored
    ])
    j = client.get("/risk").json()
    assert j["stub"] is False and j["date"] == "2026-11-20" and j["generated_at"]
    assert j["cell_deg"] == d
    assert [c["level"] for c in j["cells"]] == ["very_high", "high"]
    assert j["cells"][0]["score"] == 0.95
    assert len(j["places"]) == 1
    p = j["places"][0]
    assert p["top_factors"] == ["wind", "past fires"] and p["level"] == "very_high"
    assert abs(p["lat"] - 36.6) < d and abs(p["lon"] - 4.1) < d


def test_semicolon_factors_and_real_places(cfg, monkeypatch):
    places = pd.DataFrame({"id": ["osm:1", "osm:2", "osm:3"], "name": ["Near", "Also near", "Far"],
                           "lat": [36.61, 36.62, 36.0], "lon": [4.11, 4.12, 2.0]})
    monkeypatch.setattr(impact, "real_places", lambda: places)
    cfg["risk"]["min_flag_spacing_km"] = 0
    write_risk(cfg, [row(36.601, 4.101, 0.9, "very_high", "wind; dryness ;")])
    j = client.get("/risk").json()
    assert {p["id"] for p in j["places"]} == {"osm:1", "osm:2"}  # "Far" is outside place_radius_km
    dists = [p["distance_km"] for p in j["places"]]
    assert dists == sorted(dists)  # same score: nearest first
    assert j["places"][0]["top_factors"] == ["wind", "dryness"]
    assert all(p["distance_km"] <= cfg["risk"]["place_radius_km"] for p in j["places"])


def test_flag_spacing_and_cap(cfg):
    cfg["risk"]["max_flags"] = 2
    write_risk(cfg, [row(36.6, 4.1, 0.95, "very_high"), row(36.6, 4.15, 0.94, "very_high"),  # ~4 km apart
                     row(36.8, 5.9, 0.9, "very_high"), row(35.2, 0.5, 0.85, "very_high")])
    j = client.get("/risk").json()
    assert len(j["places"]) == 2
    assert j["places"][0]["score"] == 0.95 and j["places"][1]["score"] == 0.9


def test_bad_file_says_which_columns(cfg):
    pd.DataFrame({"lat": [36.6], "lon": [4.1]}).to_parquet(cfg["paths"]["risk_today"])
    r = client.get("/risk")
    assert r.status_code == 500 and "missing columns" in r.json()["detail"]


# ---- preventive flags ------------------------------------------------------------------------

def test_one_preventive_flag_per_place_and_day(cfg):
    write_risk(cfg, [row(36.6, 4.1, 0.95, "very_high"), row(36.8, 5.9, 0.9, "very_high"),
                     row(35.5, 1.0, 0.6, "high")])
    places = client.get("/risk").json()["places"]
    flags = pending()
    assert len(flags) == len(places) == 2
    assert {a["id"] for a in flags} == {p["alert_id"] for p in places}
    for a in flags:
        assert (a["source"], a["level"], a["status"]) == ("ai_risk", "preventive", "pending")
        assert a["fire_id"] == "risk_2026-11-20" and a["minutes_left"] is None
        assert "High fire risk today" in a["texts"]["en"]
    client.get("/risk")
    assert len(pending()) == 2  # idempotent


def test_approved_preventive_reaches_phone_and_is_not_reflagged(cfg):
    write_risk(cfg, [row(36.6, 4.1, 0.95, "very_high")])
    p = client.get("/risk").json()["places"][0]
    phone = store.broker.subscribe()
    try:
        r = client.post(f"/alerts/{p['alert_id']}/approve")
        assert r.status_code == 200 and r.json()["status"] == "sent"
        head, data = phone.get_nowait().split("\ndata: ", 1)
        a = json.loads(data)
        assert head == "event: alert" and a["level"] == "preventive" and a["village_id"] == p["id"]
    finally:
        store.broker.unsubscribe(phone)
    again = client.get("/risk").json()["places"][0]
    assert again["alert_id"] == p["alert_id"] and again["alert_status"] == "sent"
    assert pending() == []


def test_rejected_is_not_reflagged_but_reset_rearms(cfg):
    write_risk(cfg, [row(36.6, 4.1, 0.95, "very_high")])
    p = client.get("/risk").json()["places"][0]
    assert client.post(f"/alerts/{p['alert_id']}/reject", json={"reason": "already patrolled"}).status_code == 200
    assert client.get("/risk").json()["places"][0]["alert_status"] == "rejected"
    assert pending() == []
    assert client.post("/reset").status_code == 200
    client.get("/risk")
    assert len(pending()) == 1


def test_new_day_flags_again(cfg):
    write_risk(cfg, [row(36.6, 4.1, 0.95, "very_high", date="2026-11-20")])
    client.get("/risk")
    write_risk(cfg, [row(36.6, 4.1, 0.95, "very_high", date="2026-11-21")])
    client.get("/risk")
    assert sorted(a["fire_id"] for a in pending()) == ["risk_2026-11-20", "risk_2026-11-21"]
