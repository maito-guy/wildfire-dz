"""Approval queue (#24): AI flags stay pending until an operator approves; token on write endpoints."""
import json

import pytest
from fastapi.testclient import TestClient

from api.alerts import AlertStore, store
from api.main import app

TOKEN = "test-token"
client = TestClient(app, headers={"X-Operator-Token": TOKEN})
FIRE = [{"lat": 36.65, "lon": 4.10}, {"lat": 36.652, "lon": 4.104}]
T = "2021-08-09T12:00:00Z"


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setenv("OPERATOR_TOKEN", TOKEN)
    assert client.post("/reset").status_code == 200


@pytest.fixture
def queues():
    """Listen like a phone (/alerts/stream) and like a dashboard (/events)."""
    phone, dash = store.broker.subscribe(), store.events.subscribe()
    yield phone, dash
    store.broker.unsubscribe(phone)
    store.events.unsubscribe(dash)


def drain(q) -> list[tuple[str, str, str]]:
    """Queued SSE messages as (event, alert id, alert status)."""
    out = []
    while not q.empty():
        head, data = q.get_nowait().split("\ndata: ", 1)
        a = json.loads(data)
        out.append((head.removeprefix("event: "), a["id"], a["status"]))
    return out


def predict(fire_id: str | None = None) -> dict:
    r = client.post("/predict", json={"fire_id": fire_id, "burning": FIRE, "time": T,
                                      "wind": {"speed_kmh": 45, "from_deg": 270}})
    assert r.status_code == 200, r.text
    return r.json()


def village(status: str, minutes: int | None, vid: str = "v1") -> dict:
    return {"id": vid, "name": "Village X", "lat": 36.66, "lon": 4.11, "distance_km": 3.2,
            "minutes_left": minutes, "status": status, "fire_direction": "SW", "leave_toward": "NE",
            "leave_toward_deg": 31.0}


# ---- the phone never sees a flag before approval ----------------------------------------------

def test_flag_reaches_phones_only_after_approval(queues):
    phone, dash = queues
    fire = predict()["fire_id"]
    flags = client.get("/alerts", params={"status": "pending"}).json()
    assert flags and all(a["source"] == "ai_spread" for a in flags)
    assert drain(phone) == [], "a pending flag must never reach /alerts/stream"
    events = drain(dash)
    assert {e for e, _, _ in events} == {"flag"} and len(events) == len(flags)

    predict(fire)  # same fire mask again: nothing new, nothing sent
    assert drain(phone) == [] and drain(dash) == []

    a = client.post(f"/alerts/{flags[0]['id']}/approve").json()
    assert a["status"] == "sent" and a["approved_at"] and a["edited"] is False
    assert drain(phone) == [("alert", a["id"], a["status"])]
    assert drain(dash) == [("alert_sent", a["id"], a["status"])]
    assert client.get("/health").json()["pending_alerts"] == len(flags) - 1


def test_approve_with_edits():
    predict()
    fid = client.get("/alerts").json()[0]["id"]
    r = client.post(f"/alerts/{fid}/approve", json={"texts": {"en": "Edited text."}, "radius_km": 8})
    assert r.status_code == 200, r.text
    a = r.json()
    assert a["texts"]["en"] == "Edited text." and a["edited"] is True and a["area"]["radius_km"] == 8
    assert client.post(f"/alerts/{fid}/approve").status_code == 409


@pytest.mark.parametrize("body", [{"radius_km": 0}, {"radius_km": 51}, {"texts": {"xx": "hi"}},
                                  {"texts": {"en": " "}}])
def test_approve_rejects_bad_body(body):
    predict()
    fid = client.get("/alerts").json()[0]["id"]
    assert client.post(f"/alerts/{fid}/approve", json=body).status_code == 422
    assert client.get("/alerts", params={"status": "pending"}).json()[0]["id"] == fid


def test_reject_logged_with_time_and_never_sent(queues):
    phone, dash = queues
    fire = predict()["fire_id"]
    flags = client.get("/alerts").json()
    fid = flags[0]["id"]
    assert client.post(f"/alerts/{fid}/reject", json={"reason": ""}).status_code == 422
    r = client.post(f"/alerts/{fid}/reject", json={"reason": "smoke from a controlled burn"}).json()
    assert r["status"] == "rejected" and r["rejected_at"] and r["reject_reason"] == "smoke from a controlled burn"
    assert ("alert_rejected", r["id"], r["status"]) in drain(dash)
    assert client.post(f"/alerts/{fid}/reject", json={"reason": "again"}).status_code == 409
    assert client.post(f"/alerts/{fid}/approve").status_code == 409
    assert client.post("/alerts/al_9999/reject", json={"reason": "x"}).status_code == 404

    predict(fire)  # same level again: the rejected flag is not re-created
    again = [a for a in client.get("/alerts").json() if a["village_id"] == flags[0]["village_id"]]
    assert [a["id"] for a in again] == [fid]
    assert drain(phone) == []


def test_cancel_only_sent_and_logged_with_time(queues):
    phone, dash = queues
    predict()
    fid = client.get("/alerts").json()[0]["id"]
    assert client.post(f"/alerts/{fid}/cancel").status_code == 409   # still pending
    assert client.post("/alerts/al_9999/cancel").status_code == 404
    client.post(f"/alerts/{fid}/approve")
    drain(phone), drain(dash)
    c = client.post(f"/alerts/{fid}/cancel").json()
    assert c["status"] == "cancelled" and c["cancelled_at"]
    assert drain(phone) == [("cancel", c["id"], c["status"])]
    assert drain(dash) == [("alert_cancelled", c["id"], c["status"])]
    assert client.post(f"/alerts/{fid}/cancel").status_code == 409


def test_manual_alert_sent_at_once(queues):
    phone, _ = queues
    predict()
    vid = client.get("/villages/at-risk").json()["villages"][0]["id"]
    a = client.post("/alerts", json={"village_id": vid, "level": "leave_now"}).json()
    assert a["status"] == "sent" and a["source"] == "manual" and a["approved_at"]
    assert drain(phone) == [("alert", a["id"], a["status"])]


def test_list_filters_and_health():
    p = predict()
    fid = client.get("/alerts").json()[0]["id"]
    client.post(f"/alerts/{fid}/approve")
    assert [a["id"] for a in client.get("/alerts", params={"status": "sent"}).json()] == [fid]
    assert client.get("/alerts", params={"fire_id": "nope"}).json() == []
    assert len(client.get("/alerts", params={"fire_id": p["fire_id"]}).json()) >= 1
    assert client.get("/alerts", params={"status": "bogus"}).status_code == 422
    h = client.get("/health").json()
    assert {"phones_connected", "dashboards_connected", "pending_alerts"} <= set(h)


# ---- operator token ---------------------------------------------------------------------------

def _writes(fid: str, vid: str):
    return [(f"/alerts/{fid}/approve", None), (f"/alerts/{fid}/reject", {"reason": "x"}),
            (f"/alerts/{fid}/cancel", None), ("/alerts", {"village_id": vid}), ("/reset", None)]


@pytest.mark.parametrize("headers", [{}, {"X-Operator-Token": "wrong-token"}])
def test_write_endpoints_refuse_missing_or_wrong_token(headers):
    predict()
    fid = client.get("/alerts").json()[0]["id"]
    vid = client.get("/villages/at-risk").json()["villages"][0]["id"]
    anon = TestClient(app)
    for path, body in _writes(fid, vid):
        r = anon.post(path, json=body, headers=headers)
        assert r.status_code == 401, path
    assert client.get("/alerts").json()[0]["status"] == "pending"
    r = anon.post("/predict", json={"burning": FIRE, "time": T})  # stays open
    assert r.status_code == 200


def test_dev_mode_when_token_unset(monkeypatch):
    monkeypatch.setenv("OPERATOR_TOKEN", "")
    anon = TestClient(app)
    predict()
    fid = client.get("/alerts").json()[0]["id"]
    assert anon.post(f"/alerts/{fid}/approve").status_code == 200
    assert anon.post("/reset").status_code == 200


# ---- auto rule on AlertStore (no HTTP) --------------------------------------------------------

def _events(s: AlertStore):
    q = s.events.subscribe()
    return q


def test_rule_pending_flag_updates_in_place():
    s = AlertStore()
    q = _events(s)
    s.apply_rules("f", [village("get_ready", 90)], T, 0)
    s.apply_rules("f", [village("get_ready", 90)], T, 0)          # unchanged: no event
    s.apply_rules("f", [village("leave_now", 40)], T, 0)          # escalates the same card
    s.apply_rules("f", [village("get_ready", 70)], T, 0)          # level never goes down
    assert len(s.alerts) == 1
    a = next(iter(s.alerts.values()))
    assert a["status"] == "pending" and a["level"] == "leave_now" and a["minutes_left"] == 70
    assert "LEAVE NOW" in a["texts"]["en"]
    assert [e for e, _, _ in drain(q)] == ["flag", "flag_updated", "flag_updated"]


def test_rule_escalation_after_sent_and_update_on_safe():
    s = AlertStore()
    phone = s.broker.subscribe()
    first = s.apply_rules("f", [village("get_ready", 90)], T, 0)[0]
    s.approve(first["id"])
    assert s.apply_rules("f", [village("get_ready", 80)], T, 0) == []   # same level: nothing
    esc = s.apply_rules("f", [village("leave_now", 30)], T, 0)
    assert len(esc) == 1 and esc[0]["level"] == "leave_now" and esc[0]["status"] == "pending"
    s.reject(esc[0]["id"], "fire line held")
    upd = s.apply_rules("f", [village("safe", None)], T, 0)
    assert len(upd) == 1 and upd[0]["level"] == "update" and upd[0]["status"] == "pending"
    assert s.apply_rules("f", [village("safe", None)], T, 0) == []      # only one update flag
    assert [e for e, _, _ in drain(phone)] == ["alert"]                    # only the approved one
    assert s.sticky_status("f", village("safe", None)) == "leave_now"


def test_rule_rejected_not_recreated_unless_escalation():
    s = AlertStore()
    a = s.apply_rules("f", [village("get_ready", 90)], T, 0)[0]
    s.reject(a["id"], "false positive")
    assert s.apply_rules("f", [village("get_ready", 85)], T, 0) == []
    b = s.apply_rules("f", [village("leave_now", 30)], T, 0)
    assert len(b) == 1 and b[0]["level"] == "leave_now" and b[0]["id"] != a["id"]


def test_flag_helper_preventive_risk():
    s = AlertStore()
    a = s.flag("risk_2026-11-20", village("safe", None), "preventive", "ai_risk", T, 0)
    assert a["status"] == "pending" and a["level"] == "preventive" and a["source"] == "ai_risk"
    assert a["texts"]["en"].startswith("High fire risk today around Village X.")
    assert s.flag("risk_2026-11-20", village("safe", None), "preventive", "ai_risk", T, 0) is a


# ---- C's opinion orders the queue, and no flag is lost on /events (#58) -------------------------

def test_flag_update_copies_ai_opinion():
    s = AlertStore()
    q = _events(s)
    s.apply_rules("f", [village("get_ready", 90) | {"ai_opinion": "possible"}], T, 0)
    s.apply_rules("f", [village("get_ready", 90) | {"ai_opinion": "likely"}], T, 0)    # only C changed its mind
    a = next(iter(s.alerts.values()))
    assert a["ai_opinion"] == "likely"
    assert [e for e, _, _ in drain(q)] == ["flag", "flag_updated"]


def test_pending_order_opinion_then_minutes():
    from api.alerts import pending_order
    rows = [{"ai_opinion": None, "minutes_left": 10}, {"ai_opinion": "unlikely", "minutes_left": 20},
            {"ai_opinion": "likely", "minutes_left": 90}, {"ai_opinion": "possible", "minutes_left": None},
            {"ai_opinion": "possible", "minutes_left": 30}, {"ai_opinion": "likely", "minutes_left": 40}]
    got = [(r["ai_opinion"], r["minutes_left"]) for r in sorted(rows, key=pending_order)]
    assert got == [("likely", 40), ("likely", 90), ("possible", 30), ("possible", None), ("unlikely", 20),
                   (None, 10)]


def test_200_flags_from_one_predict_all_reach_events():
    s = AlertStore()
    q = _events(s)
    s.apply_rules("f", [village("get_ready", 90, f"v{i}") for i in range(200)], T, 0)
    events = drain(q)
    assert len(events) == 200 and {e for e, _, _ in events} == {"flag"}


def _raw(q) -> list[str]:
    out = []
    while not q.empty():
        out.append(q.get_nowait().split("\n", 1)[0].removeprefix("event: "))
    return out


def test_dashboard_far_behind_gets_resync(monkeypatch, caplog):
    import api.alerts as alerts_mod
    cfg = alerts_mod.load_config()
    monkeypatch.setattr(alerts_mod, "load_config", lambda: {**cfg, "api": {**cfg["api"], "events_queue_size": 10}})
    s = AlertStore()
    dash, phone = s.events.subscribe(), s.broker.subscribe()
    with caplog.at_level("WARNING", logger="api.alerts"):
        flags = s.apply_rules("f", [village("get_ready", 90, f"v{i}") for i in range(25)], T, 0)
        for a in flags[:12]:
            s.approve(a["id"])                                   # 12 sent alerts for a phone with room for 10
    got = _raw(dash)
    assert got[0] == "resync" and len(got) <= 10                 # the dashboard refetches /alerts instead
    assert "resync" not in _raw(phone)                           # phones never get resync, only a logged drop
    assert any("resync sent" in r.message for r in caplog.records)
    assert any("alerts/stream" in r.message and "dropped" in r.message for r in caplog.records)
    assert len(s.alerts) == 25                                   # the flags themselves are all in the store
