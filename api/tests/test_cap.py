"""CAP 1.2 message (#26): valid against the OASIS schema, served once an alert is published, hand-off logged."""
import datetime as dt
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from lxml import etree

from api import cap
from api.alerts import store
from api.main import app
from core.config import load_config

TOKEN = "test-token"
client = TestClient(app, headers={"X-Operator-Token": TOKEN})
SCHEMA = etree.XMLSchema(etree.parse(str(Path(__file__).parent / "data" / "CAP-v1.2.xsd")))
NS = {"cap": cap.NS}
T = dt.datetime(2021, 8, 9, 12, 0, tzinfo=dt.UTC)


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    monkeypatch.setenv("OPERATOR_TOKEN", TOKEN)
    assert client.post("/reset").status_code == 200


def village(vid: str = "v1", minutes: int | None = 31) -> dict:
    return {"id": vid, "name": "Village X", "lat": 36.66, "lon": 4.11, "distance_km": 1.04,
            "minutes_left": minutes, "status": "leave_now", "fire_direction": "SW", "leave_toward": "NE",
            "leave_toward_deg": 31.0}


def parse(xml: str) -> etree._Element:
    assert xml.startswith('<?xml version="1.0" encoding="UTF-8"?>')
    doc = etree.fromstring(xml.encode("utf-8"))
    SCHEMA.assertValid(doc)
    return doc


def text(doc, path: str) -> str:
    return doc.findtext(path, namespaces=NS)


@pytest.mark.parametrize("level, response, uscert", [
    ("leave_now", "Evacuate", ("Immediate", "Extreme", "Likely")),
    ("get_ready", "Prepare", ("Expected", "Severe", "Likely")),
    ("preventive", "Monitor", ("Future", "Moderate", "Possible")),
    ("update", "Monitor", ("Expected", "Moderate", "Possible")),
])
def test_each_level_validates_and_maps(level, response, uscert):
    a = store.flag("fire_001", village(), level, "ai_spread", T, 47)
    a["texts"] = {"en": "English text.", "fr": "Texte.", "ar": "نص", "ary": "نص دارجة", "kab": "Aḍris."}
    a = store.approve(a["id"])
    doc = parse(cap.build_cap(a, load_config()))

    assert text(doc, "cap:identifier") == f"DZ.WILDFIRE.{a['id']}"
    assert text(doc, "cap:sender") == "alerts@civil-protection.example.dz"
    assert text(doc, "cap:sent") == cap.cap_time(a["approved_at"])
    assert text(doc, "cap:status") == "Exercise"
    assert text(doc, "cap:msgType") == "Alert"
    assert text(doc, "cap:scope") == "Public"
    assert doc.find("cap:references", NS) is None

    infos = doc.findall("cap:info", NS)
    assert [text(i, "cap:language") for i in infos] == ["en", "fr-DZ", "ar-DZ", "ar-DZ", "kab-DZ"]
    for i in infos:
        assert text(i, "cap:category") == "Fire"
        assert text(i, "cap:event") == "Wildfire"
        assert text(i, "cap:responseType") == response
        assert (text(i, "cap:urgency"), text(i, "cap:severity"), text(i, "cap:certainty")) == uscert
        assert text(i, "cap:senderName") == "Protection Civile — simulated"
        assert text(i, "cap:headline")  # en master headline as fallback
        assert i.find("cap:instruction", NS) is None and i.find("cap:web", NS) is None
        assert text(i, "cap:area/cap:areaDesc") == "Village X"
        assert text(i, "cap:area/cap:circle") == "36.66,4.11 5"
        params = {text(p, "cap:valueName"): text(p, "cap:value") for p in i.findall("cap:parameter", NS)}
        assert params == {"minutes_left": "31", "distance_km": "1.04", "leave_toward": "NE",
                          "data_age_min": "47", "wildfire_alert_id": a["id"]}
    assert [text(i, "cap:description") for i in infos] == list(a["texts"].values())


def test_cancel_references_the_original_and_validates():
    a = store.send("fire_001", village(minutes=None), "leave_now", "manual", T, 0)
    original = parse(cap.build_cap(a, load_config()))
    a = store.cancel(a["id"])
    doc = parse(cap.build_cap(a, load_config()))

    assert text(doc, "cap:msgType") == "Cancel"
    assert text(doc, "cap:identifier") != text(original, "cap:identifier")
    assert text(doc, "cap:sent") == cap.cap_time(a["cancelled_at"])
    assert text(doc, "cap:references") == ",".join(
        text(original, f"cap:{k}") for k in ("sender", "identifier", "sent"))
    # minutes_left = null is left out rather than sent as an empty value
    names = [text(p, "cap:valueName") for p in doc.findall("cap:info/cap:parameter", NS)]
    assert "minutes_left" not in names


def test_explicit_references_are_used():
    a = store.cancel(store.send("fire_001", village(), "get_ready", "manual", T, 0)["id"])
    ref = {"sender": "s@x.dz", "identifier": "X.1", "sent": "2021-08-09T12:00:00+00:00"}
    doc = parse(cap.build_cap(a, load_config(), references=ref))
    assert text(doc, "cap:references") == "s@x.dz,X.1,2021-08-09T12:00:00+00:00"


def test_cap_time_is_utc_without_fraction():
    t = dt.datetime(2026, 11, 20, 8, 38, 2, 123456, tzinfo=dt.timezone(dt.timedelta(hours=1)))
    assert cap.cap_time(t) == "2026-11-20T07:38:02+00:00"
    assert cap.cap_time("2026-11-20T07:38:02Z") == "2026-11-20T07:38:02+00:00"


# ---- endpoint -----------------------------------------------------------------------------------

def test_endpoint_serves_sent_and_cancelled():
    a = store.send("fire_001", village(), "leave_now", "manual", T, 0)
    r = client.get(f"/alerts/{a['id']}/cap.xml", headers={"X-Operator-Token": ""})
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/xml")
    assert text(parse(r.text), "cap:msgType") == "Alert"

    assert client.post(f"/alerts/{a['id']}/cancel").status_code == 200
    r = client.get(f"/alerts/{a['id']}/cap.xml")
    assert r.status_code == 200
    assert text(parse(r.text), "cap:msgType") == "Cancel"


def test_endpoint_409_for_unpublished_and_404_unknown():
    pending = store.flag("fire_001", village("v1"), "leave_now", "ai_spread", T, 0)
    rejected = store.reject(store.flag("fire_001", village("v2"), "get_ready", "ai_spread", T, 0)["id"], "smoke")
    assert client.get(f"/alerts/{pending['id']}/cap.xml").status_code == 409
    assert client.get(f"/alerts/{rejected['id']}/cap.xml").status_code == 409
    assert client.get("/alerts/al_9999/cap.xml").status_code == 404


# ---- simulated cell-broadcast hand-off ----------------------------------------------------------

def test_handoff_logged_on_approve_and_cancel(caplog):
    caplog.set_level(logging.INFO, logger="api.cap")
    a = store.flag("fire_001", village(), "leave_now", "ai_spread", T, 0)
    assert not [r for r in caplog.records if r.name == "api.cap"]  # a pending flag is never handed off
    assert client.post(f"/alerts/{a['id']}/approve").status_code == 200
    assert client.post(f"/alerts/{a['id']}/cancel").status_code == 200
    lines = [r.getMessage() for r in caplog.records if r.name == "api.cap"]
    assert lines == [
        f"CBC hand-off (simulated): DZ.WILDFIRE.{a['id']} Alert area=36.66,4.11 5 km",
        f"CBC hand-off (simulated): DZ.WILDFIRE.{a['id']}.cancel Cancel area=36.66,4.11 5 km",
    ]
