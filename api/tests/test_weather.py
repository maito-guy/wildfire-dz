"""api.weather.get_wind with mocked HTTP: forecast, archive (ERA5), fallback, cache."""
import asyncio
import datetime as dt

import httpx
from fastapi.testclient import TestClient

from api import weather
from api.main import app
from core.config import load_config

CFG = load_config()
LAT, LON = 36.65, 4.10


def _hourly(day: dt.date, speed=30.0, deg=200.0, missing_hour=None):
    times = [f"{day.isoformat()}T{h:02d}:00" for h in range(24)]
    spd = [speed + h for h in range(24)]
    dirs = [deg] * 24
    if missing_hour is not None:
        spd[missing_hour] = None
    return {"hourly": {"time": times, "wind_speed_10m": spd, "wind_direction_10m": dirs}}


def _client(handler, calls):
    def wrapped(request):
        calls.append(request)
        return handler(request)
    return httpx.AsyncClient(transport=httpx.MockTransport(wrapped))


def _run(at, handler, calls):
    async def go():
        async with _client(handler, calls) as c:
            return await weather.get_wind(LAT, LON, at, CFG, client=c)
    return asyncio.run(go())


def test_recent_time_uses_forecast_nearest_hour():
    at = (dt.datetime.now(dt.UTC) - dt.timedelta(hours=3)).replace(minute=10)
    calls = []
    wind, src = _run(at, lambda r: httpx.Response(200, json=_hourly(at.date())), calls)
    assert src == "forecast"
    assert wind == {"speed_kmh": 30.0 + at.hour, "from_deg": 200.0}    # :10 rounds down to the hour
    url = calls[0].url
    assert str(url).startswith(CFG["forecast"]["forecast_url"])
    q = url.params
    assert q["hourly"] == "wind_speed_10m,wind_direction_10m"
    assert q["wind_speed_unit"] == "kmh" and q["timezone"] == "UTC"
    assert q["start_date"] == q["end_date"] == at.date().isoformat()


def test_2021_uses_archive():
    at = dt.datetime(2021, 8, 9, 11, 40, tzinfo=dt.UTC)                 # nearest hour = 12:00
    calls = []
    wind, src = _run(at, lambda r: httpx.Response(200, json=_hourly(at.date())), calls)
    assert src == "reanalysis" and wind == {"speed_kmh": 42.0, "from_deg": 200.0}
    assert str(calls[0].url).startswith(CFG["forecast"]["archive_url"])
    assert calls[0].url.params["start_date"] == "2021-08-09" == calls[0].url.params["end_date"]


def test_timeout_falls_back_to_config_default():
    def boom(request):
        raise httpx.ReadTimeout("slow", request=request)
    wind, src = _run(dt.datetime.now(dt.UTC), boom, [])
    assert src == "config_default" and wind == CFG["weather_default"]


def test_http_error_and_missing_value_fall_back():
    at = dt.datetime(2021, 8, 9, 12, tzinfo=dt.UTC)
    assert _run(at, lambda r: httpx.Response(500), [])[1] == "config_default"
    wind, src = _run(at, lambda r: httpx.Response(200, json=_hourly(at.date(), missing_hour=12)), [])
    assert src == "config_default" and wind == CFG["weather_default"]


def test_cache_hit_avoids_second_call():
    at = dt.datetime(2021, 8, 9, 12, tzinfo=dt.UTC)
    calls = []
    handler = lambda r: httpx.Response(200, json=_hourly(at.date()))     # noqa: E731
    first = _run(at, handler, calls)
    again = _run(at, handler, calls)
    same_day = _run(at + dt.timedelta(hours=3), handler, calls)          # other hours of the response are cached too
    assert len(calls) == 1
    assert first == again and first[1] == "reanalysis"
    assert same_day == ({"speed_kmh": 45.0, "from_deg": 200.0}, "reanalysis")


def test_predict_without_wind_uses_weather(monkeypatch):
    async def fake(lat, lon, at, cfg, client=None):
        assert 36.6 < lat < 36.7 and 4.0 < lon < 4.2
        return {"speed_kmh": 12.5, "from_deg": 90.0}, "forecast"
    monkeypatch.setattr(weather, "get_wind", fake)
    p = TestClient(app).post("/predict", json={"burning": [{"lat": LAT, "lon": LON}]}).json()
    assert p["wind_source"] == "forecast" and p["wind"] == {"speed_kmh": 12.5, "from_deg": 90.0}


def test_predict_offline_falls_back():
    p = TestClient(app).post("/predict", json={"burning": [{"lat": LAT, "lon": LON}]}).json()
    assert p["wind_source"] == "config_default"
    assert p["wind"] == {k: float(v) for k, v in CFG["weather_default"].items()}
