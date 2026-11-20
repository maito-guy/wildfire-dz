"""Smoke test: every contract endpoint answers with the right shape (stub data)."""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from api.alerts import Broker
from api.main import app

client = TestClient(app, headers={"X-Operator-Token": "test-token"})
FIRE = [{"lat": 36.65, "lon": 4.10}, {"lat": 36.652, "lon": 4.104}]


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setenv("OPERATOR_TOKEN", "test-token")
    assert client.post("/reset").status_code == 200


def test_health_and_static():
    assert client.get("/health").json()["ok"] is True
    assert client.get("/dashboard/").status_code == 200
    assert client.get("/alert/").status_code == 200


def test_predict_villages_alerts_flow():
    r = client.post("/predict", json={"burning": FIRE, "time": "2021-08-09T12:00:00Z",
                                      "observed_at": "2021-08-09T11:13:00Z",
                                      "wind": {"speed_kmh": 45, "from_deg": 270}})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["model"] == "B" and p["data_age_min"] == 47 and p["embers_applied"] is True
    assert {f["properties"]["horizon_min"] for f in p["zones"]["features"]} == {60, 120}
    assert all(c["arrival_min"] <= 120 for c in p["cells"])

    v = client.get("/villages/at-risk", params={"fire_id": p["fire_id"]}).json()
    assert v["villages"], "stub villages expected around the fire"
    first = v["villages"][0]
    assert first["status"] in {"safe", "get_ready", "leave_now"}
    assert set(first) >= {"id", "name", "lat", "lon", "minutes_left", "status", "leave_toward"}

    flags = client.get("/alerts").json()
    assert flags, "pending flags expected for villages under 120 min"
    assert all(a["status"] == "pending" and a["source"] == "ai_spread" for a in flags)
    assert "en" in flags[0]["texts"]
    assert client.get("/health").json()["pending_alerts"] == len(flags)
    s = client.post(f"/alerts/{flags[0]['id']}/approve").json()
    assert s["status"] == "sent" and s["approved_at"]
    c = client.post(f"/alerts/{flags[0]['id']}/cancel").json()
    assert c["status"] == "cancelled"
    m = client.post("/alerts", json={"village_id": first["id"], "level": "leave_now"})
    assert m.status_code == 200 and m.json()["source"] == "manual"


def test_point_start_and_scope():
    r = client.post("/predict", json={"burning": [{"lat": 36.5, "lon": 3.0}], "model": "C"})
    assert r.json()["model"] == "B" and r.json()["fallback_reason"]   # fail-safe to B
    assert client.post("/predict", json={"burning": [{"lat": 30.0, "lon": 3.0}]}).status_code == 422


def test_replay_and_scoreboard():
    fires = client.get("/replay").json()
    passes = client.get(f"/replay/{fires[0]['fire_id']}").json()["passes"]
    assert passes and passes[0]["burning"]
    assert "status" in client.get("/scoreboard").json() or "fires" in client.get("/scoreboard").json()


def test_broker_fanout():
    async def run():
        b = Broker()
        q = b.subscribe()
        b.publish("alert", {"id": "al_0001"})
        msg = await asyncio.wait_for(q.get(), 1)
        assert msg.startswith("event: alert") and json.loads(msg.split("data: ")[1])["id"] == "al_0001"
    asyncio.run(run())
