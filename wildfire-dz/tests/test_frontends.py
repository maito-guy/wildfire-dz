"""Smoke tests for dashboard/ and alert/ (static files): they exist and speak the contract."""
import json
import string

from core.config import ROOT


def read(p):
    return (ROOT / p).read_text(encoding="utf-8")


def test_dashboard_uses_contract_endpoints():
    js = read("dashboard/app.js")
    for ep in ("/predict", "/villages/at-risk", "/alerts", "/replay"):
        assert ep in js, ep
    assert "vendor/leaflet/leaflet.js" in read("dashboard/index.html")
    assert (ROOT / "dashboard/vendor/leaflet/leaflet.js").exists()


def test_alert_page_listens_to_stream():
    js = read("alert/alert.js")
    assert "/alerts/stream" in js and "EventSource" in js
    assert 'addEventListener("cancel"' in js


def test_alert_texts_have_english_masters_and_valid_placeholders():
    t = json.loads(read("alert/texts.json"))
    allowed = {"village", "km", "direction", "minutes", "leave_toward", "phone"}
    for level in ("get_ready", "leave_now", "update"):
        assert t["templates"][level]["en"], level
        for lang, tpl in t["templates"][level].items():
            used = {f for _, f, _, _ in string.Formatter().parse(tpl) if f}
            assert used <= allowed, (level, lang, used - allowed)
