"""GET /detections and GET /history (#29): stub fallback, filters on real files, history aggregation."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api import detections
from api.main import app
from core.config import load_config

client = TestClient(app)


@pytest.fixture
def paths(tmp_path, monkeypatch):
    """Point both fire-map paths at an empty temp dir (no file = stub)."""
    p = load_config()["paths"]
    monkeypatch.setitem(p, "detections", str(tmp_path / "detections.parquet"))
    monkeypatch.setitem(p, "history_grid", str(tmp_path / "history_grid.parquet"))
    return tmp_path


def _row(lat, lon, t, **kw):
    return {"lat": lat, "lon": lon, "t": pd.Timestamp(t, tz="UTC"), "sat": "NOAA20", "frp": 12.5,
            "conf": "n", "daynight": "D", "country": "DZA", **kw}


def test_stub_detections(paths):
    r = client.get("/detections")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["stub"] is True and d["count"] == len(d["detections"]) > 0 and d["truncated"] is False
    ts = [pd.Timestamp(x["t"]) for x in d["detections"]]
    assert ts == sorted(ts, reverse=True), "newest first"
    newest, since = pd.Timestamp(d["newest"]), pd.Timestamp(d["since"])
    assert ts[0] == newest and newest - since == pd.Timedelta(hours=load_config()["fire_map"]["default_hours"])
    assert all(x["lat"] >= 34.5 for x in d["detections"])
    assert set(d["detections"][0]) >= {"lat", "lon", "t", "satellite", "frp"}
    assert client.get("/detections").json() == d, "stub is deterministic"

    older = client.get("/detections", params={"since": "2026-07-01T00:00:00Z"}).json()
    assert older["count"] > d["count"], "an older fire sits outside the default 7-day window"
    day = client.get("/detections", params={"since": (newest - pd.Timedelta(hours=24)).isoformat()}).json()
    assert 0 < day["count"] < d["count"]
    bad = client.get("/detections", params={"since": "2026-09-01T00:00:00Z", "until": "2026-08-01T00:00:00Z"})
    assert bad.status_code == 422


def test_real_detections_filtered(paths, monkeypatch):
    rows = [_row(36.7, 4.2, "2026-08-30T12:00"),                      # kept
            _row(30.0, 5.0, "2026-08-30T12:00"),                      # Sahara: south of 34.5
            _row(36.8, 9.5, "2026-08-30T12:00", country="TUN"),       # Tunisia
            _row(36.6, 4.3, "2026-08-30T12:00", flare=True)]          # flagged flare
    rows[0]["flare"] = False
    for i in range(16):                                               # gas flare: same block, 16 days, 4 years
        rows.append(_row(36.0, 6.0, f"{2022 + i % 4}-07-{1 + i:02d}T01:30"))
    pd.DataFrame(rows).to_parquet(paths / "detections.parquet")
    d = client.get("/detections", params={"since": "2012-01-01T00:00:00Z"}).json()
    assert d["stub"] is False and d["count"] == 1
    x = d["detections"][0]
    assert (x["lat"], x["lon"], x["satellite"], x["frp"]) == (36.7, 4.2, "NOAA20", 12.5)
    assert d["newest"] == "2026-08-30T12:00:00Z"

    monkeypatch.setitem(load_config()["fire_map"], "max_points", 0)
    assert client.get("/detections").json()["truncated"] is True


def test_real_detections_without_country_use_bbox(paths):
    pd.DataFrame([{"lat": 36.7, "lon": 4.2, "t": pd.Timestamp("2026-08-30", tz="UTC")},
                  {"lat": 36.8, "lon": 9.5, "t": pd.Timestamp("2026-08-30", tz="UTC")}]
                 ).to_parquet(paths / "detections.parquet")
    d = client.get("/detections").json()
    assert d["count"] == 1 and d["detections"][0]["satellite"] is None


def test_stub_history_shows_kabylie_2021(paths):
    h = client.get("/history").json()
    assert h["stub"] is True and h["source"] == "stub" and h["cells"]
    assert (h["first_year"], h["last_year"]) == (2012, 2026)
    top = max(h["cells"], key=lambda c: c["count"])
    lon_min, lat_min, lon_max, lat_max = load_config()["holdouts"]["kabylie_2021"]["bbox"]
    assert lat_min <= top["lat"] <= lat_max and lon_min <= top["lon"] <= lon_max
    assert top["count"] == h["max_count"]


def test_history_from_detections_then_grid(paths):
    rows = [_row(36.71, 4.21, "2021-08-10T01:00"), _row(36.72, 4.22, "2021-08-10T13:00"),
            _row(36.71, 4.21, "2023-07-01T13:00"), _row(36.9, 7.9, "2019-08-01T13:00")]
    pd.DataFrame(rows).to_parquet(paths / "detections.parquet")
    h = client.get("/history").json()
    assert h["source"] == "detections" and h["stub"] is False
    top = max(h["cells"], key=lambda c: c["count"])
    assert (top["count"], top["years"], top["last_year"]) == (3, 2, 2023)
    assert (h["first_year"], h["last_year"], h["max_count"]) == (2019, 2023, 3)

    assert detections.main(["build-history"]) == 0
    g = pd.read_parquet(paths / "history_grid.parquet")
    assert set(g.columns) >= {"lat", "lon", "count", "years", "first_year", "last_year"} and g["count"].sum() == 4

    pd.DataFrame([{"lat": 36.7, "lon": 4.2, "count": 9}, {"lat": 30.0, "lon": 5.0, "count": 50}]
                 ).to_parquet(paths / "history_grid.parquet")
    h = client.get("/history").json()
    assert h["source"] == "grid" and len(h["cells"]) == 1 and h["max_count"] == 9
    assert h["cells"][0]["years"] is None and h["last_year"] is None


def test_build_history_cli_needs_detections(paths):
    assert detections.main(["build-history"]) == 1
    assert detections.main([]) == 2
