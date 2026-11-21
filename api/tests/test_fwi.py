"""Fire weather cap on the risk layer (#57): FWI equations, Open-Meteo request, cap table, fallback."""
import copy
import datetime as dt

import httpx
import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api import fwi, impact, risk
from api.alerts import store
from api.main import app
from core.config import load_config

TOKEN = "test-token"
client = TestClient(app, headers={"X-Operator-Token": TOKEN})

# Van Wagner & Pickett (1985) test data, 13-17 April, starting from FFMC 85, DMC 6, DC 15:
# (temp, rh, wind, rain) -> (FFMC, DMC, DC, ISI, BUI, FWI)
VAN_WAGNER = [
    ((17.0, 42, 25, 0.0), (87.7, 8.5, 19.0, 10.9, 8.5, 10.1)),
    ((20.0, 21, 25, 2.4), (86.2, 10.4, 23.6, 8.8, 10.4, 9.3)),
    ((8.5, 40, 17, 0.0), (87.0, 11.8, 26.1, 6.5, 11.7, 7.6)),
    ((6.5, 25, 6, 0.0), (88.8, 13.2, 28.2, 4.9, 13.1, 6.2)),
    ((13.0, 34, 24, 0.0), (89.1, 15.4, 31.5, 12.6, 15.3, 14.8)),
]


def test_van_wagner_test_values():
    f, p, d = fwi.START_FFMC, fwi.START_DMC, fwi.START_DC
    for (t, h, w, r), want in VAN_WAGNER:
        f, p, d = float(fwi.ffmc(t, h, w, r, f)), float(fwi.dmc(t, h, r, p, 4)), float(fwi.dc(t, r, d, 4))
        i, u = float(fwi.isi(w, f)), float(fwi.bui(p, d))
        got = (f, p, d, i, u, float(fwi.fwi(i, u)))
        assert [round(x, 1) for x in got] == pytest.approx(list(want), abs=0.11)


def test_run_matches_day_by_day_and_skips_missing():
    days = [dt.date(2026, 4, 13 + k) for k in range(len(VAN_WAGNER))]
    cols = np.array([w for w, _ in VAN_WAGNER], dtype=float)   # (days, 4)
    t, h, w, r = (np.stack([cols[:, k], cols[:, k]], axis=1) for k in range(4))
    t[2, 1] = np.nan  # point 1 misses a middle day: codes unchanged that day, still a value at the end
    out = fwi.run(days, t, h, w, r)
    assert out[0] == pytest.approx(14.8, abs=0.11)
    assert np.isfinite(out[1]) and out[1] != out[0]
    t[-1, 1] = np.nan
    assert np.isnan(fwi.run(days, t, h, w, r)[1])


def test_classify_uses_effis_bounds():
    classes = load_config()["risk"]["fwi"]["classes"]
    assert fwi.classify(0.0, classes) == "very_low"
    assert fwi.classify(5.2, classes) == "low"
    assert fwi.classify(21.0, classes) == "moderate"
    assert fwi.classify(31.0, classes) == "high"
    assert fwi.classify(45.0, classes) == "very_high"
    assert fwi.classify(70.0, classes) == "extreme"


def test_nearest_point_on_grid():
    c = load_config()
    la, lo = fwi.grid(c)
    k = fwi.nearest(c, [36.74, 34.5], [4.1, -2.3])
    assert la[k[0]] == pytest.approx(36.5) and lo[k[0]] == pytest.approx(4.2)
    assert la[k[1]] == pytest.approx(34.5) and lo[k[1]] == pytest.approx(-2.3)


# ---- Open-Meteo (mocked) ----------------------------------------------------------------------

CALM = {"temperature_2m_max": 12.0, "relative_humidity_2m_min": 85.0, "wind_speed_10m_mean": 8.0,
        "precipitation_sum": 6.0}
SIROCCO = {"temperature_2m_max": 44.0, "relative_humidity_2m_min": 8.0, "wind_speed_10m_mean": 45.0,
           "precipitation_sum": 0.0}


def weather_transport(weather: dict, seen: list):
    """Answers like Open-Meteo: one result per asked location, the same daily values every day."""
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        q = request.url.params
        n = len(q["latitude"].split(","))
        start, end = dt.date.fromisoformat(q["start_date"]), dt.date.fromisoformat(q["end_date"])
        days = [(start + dt.timedelta(days=k)).isoformat() for k in range((end - start).days + 1)]
        res = {"daily": {"time": days, **{k: [v] * len(days) for k, v in weather.items()}}}
        return httpx.Response(200, json=[res] * n if n > 1 else res)
    return httpx.MockTransport(handler)


def use_weather(monkeypatch, weather: dict | None) -> list:
    seen: list = []
    if weather is None:
        return seen   # conftest: offline
    monkeypatch.setattr(fwi, "_make_client",
                        lambda timeout_s: httpx.AsyncClient(transport=weather_transport(weather, seen)))
    return seen


@pytest.mark.anyio
async def test_one_batched_request_and_cache(monkeypatch):
    c = load_config()
    seen = use_weather(monkeypatch, SIROCCO)
    pts = fwi.nearest(c, [36.7, 36.71, 35.2], [4.1, 4.12, 0.6])  # two cells share a point
    out = await fwi.for_day("2021-08-10", c, pts)
    assert len(seen) == 1
    q = seen[0].url.params
    assert len(q["latitude"].split(",")) == 2 and q["end_date"] == "2021-08-10"
    assert q["start_date"] == (dt.date(2021, 8, 10) - dt.timedelta(days=c["risk"]["fwi"]["spinup_days"])).isoformat()
    assert str(seen[0].url).startswith(c["forecast"]["archive_url"]) and out["source"] == "reanalysis"
    assert len(out["points"]) == 2 and all(v > 50 for v in out["points"].values())
    await fwi.for_day("2021-08-10", c, pts)
    assert len(seen) == 1   # cached


@pytest.mark.anyio
async def test_recent_day_uses_forecast_api(monkeypatch):
    c = load_config()
    seen = use_weather(monkeypatch, CALM)
    day = dt.datetime.now(dt.UTC).date().isoformat()
    out = await fwi.for_day(day, c, fwi.nearest(c, [36.7], [4.1]))
    assert str(seen[0].url).startswith(c["forecast"]["forecast_url"]) and out["source"] == "forecast"
    assert list(out["points"].values())[0] < 5.2


@pytest.mark.anyio
async def test_failure_returns_none_and_is_not_cached(monkeypatch):
    c = load_config()
    assert await fwi.for_day("2021-08-10", c, fwi.nearest(c, [36.7], [4.1])) is None   # offline (conftest)
    assert not fwi._cache
    bad = httpx.MockTransport(lambda r: httpx.Response(200, json={"error": True, "reason": "nope"}))
    monkeypatch.setattr(fwi, "_make_client", lambda timeout_s: httpx.AsyncClient(transport=bad))
    assert await fwi.for_day("2021-08-10", c, fwi.nearest(c, [36.7], [4.1])) is None


@pytest.fixture
def anyio_backend():
    return "asyncio"


# ---- GET /risk with the cap ---------------------------------------------------------------------

@pytest.fixture
def cfg(monkeypatch, tmp_path):
    c = copy.deepcopy(load_config())
    c["paths"]["risk_today"] = str(tmp_path / "risk_today.parquet")
    monkeypatch.setattr(risk, "load_config", lambda: c)
    monkeypatch.setattr(impact, "real_places", lambda: None)
    monkeypatch.setenv("OPERATOR_TOKEN", TOKEN)
    assert client.post("/reset").status_code == 200
    yield c
    store.reset()


def write_cells(c: dict, date: str) -> None:
    rows = [{"date": date, "lat": 36.62, "lon": 4.12, "score": 0.95, "level": "very_high", "top_factors": "wind"},
            {"date": date, "lat": 36.92, "lon": 7.2, "score": 0.7, "level": "high", "top_factors": "dryness"},
            {"date": date, "lat": 35.3, "lon": 0.4, "score": 0.4, "level": "moderate", "top_factors": "past fires"}]
    pd.DataFrame(rows).to_parquet(c["paths"]["risk_today"])


@pytest.mark.parametrize("date", ["2026-01-15", "2025-06-20"])   # a winter day and a calm summer day
def test_calm_day_caps_levels_and_makes_no_flags(cfg, monkeypatch, date):
    write_cells(cfg, date)
    use_weather(monkeypatch, CALM)
    j = client.get("/risk").json()
    assert j["fwi"]["level"] in ("very_low", "low") and j["fwi"]["capped_cells"] == 2 and j["fwi_note"] is None
    assert {c["level"] for c in j["cells"]} == {"moderate"}
    assert j["places"] == []
    assert client.get("/alerts", params={"status": "pending"}).json() == []


def test_kabylie_day_keeps_levels_and_flags(cfg, monkeypatch):
    write_cells(cfg, "2021-08-10")
    use_weather(monkeypatch, SIROCCO)
    j = client.get("/risk").json()
    assert j["fwi"]["level"] == "extreme" and j["fwi"]["capped_cells"] == 0 and j["fwi"]["source"] == "reanalysis"
    assert {c["level"] for c in j["cells"]} == {"very_high", "high", "moderate"}
    assert len(j["places"]) == 1


def test_weather_failure_leaves_levels_and_says_so(cfg):
    write_cells(cfg, "2021-08-10")   # offline (conftest)
    j = client.get("/risk").json()
    assert j["fwi"] is None and "not capped" in j["fwi_note"]
    assert any(c["level"] == "very_high" for c in j["cells"]) and len(j["places"]) == 1


def test_cap_table_is_config(cfg, monkeypatch):
    cfg["risk"]["fwi"]["cap"] = {"very_low": "low", "low": "low", "moderate": "low", "high": "low",
                                 "very_high": "low", "extreme": "low"}
    write_cells(cfg, "2021-08-10")
    use_weather(monkeypatch, SIROCCO)
    j = client.get("/risk").json()
    assert j["cells"] == [] and j["fwi"]["capped_cells"] == 3   # everything capped to low, below min_level_shown


def test_disabled_means_no_call_and_no_note(cfg, monkeypatch):
    cfg["risk"]["fwi"]["enabled"] = False
    write_cells(cfg, "2021-08-10")
    seen = use_weather(monkeypatch, CALM)
    j = client.get("/risk").json()
    assert seen == [] and j["fwi"] is None and j["fwi_note"] is None
    assert any(c["level"] == "very_high" for c in j["cells"])
