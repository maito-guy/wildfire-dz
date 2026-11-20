import json

from fastapi.testclient import TestClient

from api import scoreboard
from api.main import app
from core.config import load_config

client = TestClient(app)


def _point_artifacts(monkeypatch, tmp_path):
    cfg = load_config()
    fake = {**cfg, "paths": {**cfg["paths"], "artifacts": str(tmp_path)}}
    monkeypatch.setattr(scoreboard, "load_config", lambda: fake)
    return cfg


def test_stub_when_file_missing(monkeypatch, tmp_path):
    cfg = _point_artifacts(monkeypatch, tmp_path)
    b = client.get("/scoreboard").json()
    assert b["stub"] is True
    assert [f["holdout"] for f in b["fires"]] == list(cfg["holdouts"])
    for f in b["fires"]:
        assert set(f["models"]) == {"A", "B", "C_mixed", "C_dza"}
        for m in f["models"].values():
            assert all(m[k] is None for k in scoreboard.METRICS)   # never invented numbers
    c = b["replay_counter"]
    assert c["lead_min"] is None and c["old_method_lead_min"] is None
    assert b["weather_note"] and b["ship_c"]["decision"] == "not measured yet"


def test_real_file_served_as_is(monkeypatch, tmp_path):
    _point_artifacts(monkeypatch, tmp_path)
    real = {"generated_at": "2026-11-21T10:00:00+00:00", "weather_note": "x", "fires": []}
    (tmp_path / "scoreboard.json").write_text(json.dumps(real))
    assert client.get("/scoreboard").json() == real
