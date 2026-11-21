"""Wind at a point and time from Open-Meteo, with the config default as fallback.

- `at` inside the forecast window (now - forecast.past_days .. now + 7 days) -> forecast API ("forecast").
- `at` older than that -> archive API, ERA5 ("reanalysis").
- Any error, timeout, or missing value -> config.yaml weather_default ("config_default").

The wind is averaged from the hour nearest `at` (UTC) over the next `forecast.mean_hours` hours, as a
vector (350 and 10 deg average to 0, not 180), speed = length of the mean vector: the same definition
as the training features wind_speed_2h / wind_from_2h (data/firedata/05_build_table.py, weather_at).
mean_hours = 0 uses that one hour only. Successful lookups are cached in memory per
(lat 2 dp, lon 2 dp, hour) for forecast.cache_min minutes; every hour of a response is cached,
so replay passes on the same day hit the cache.
"""
from __future__ import annotations

import datetime as dt
import logging
import math
import time

import httpx

log = logging.getLogger(__name__)

FORECAST_DAYS_AHEAD = 7
_cache: dict[tuple[float, float, dt.datetime], tuple[float, dict]] = {}   # key -> (expires monotonic, wind)


def _make_client(timeout_s: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout_s)


def _nearest_hour(at: dt.datetime) -> dt.datetime:
    at = at.replace(tzinfo=dt.UTC) if at.tzinfo is None else at.astimezone(dt.UTC)
    return (at + dt.timedelta(minutes=30)).replace(minute=0, second=0, microsecond=0)


def mean_wind(winds: list[dict]) -> dict:
    """Vector mean of hourly winds; speed = length of the mean vector (like wind_speed_2h in training)."""
    u = sum(w["speed_kmh"] * math.sin(math.radians(w["from_deg"])) for w in winds) / len(winds)
    v = sum(w["speed_kmh"] * math.cos(math.radians(w["from_deg"])) for w in winds) / len(winds)
    return {"speed_kmh": round(math.hypot(u, v), 2), "from_deg": round(math.degrees(math.atan2(u, v)), 1) % 360}   # round first: 359.99 -> 0, never 360


def _key(lat: float, lon: float, hour: dt.datetime) -> tuple[float, float, dt.datetime]:
    return (round(lat, 2), round(lon, 2), hour)


async def get_wind(lat: float, lon: float, at: dt.datetime, cfg: dict,
                   client: httpx.AsyncClient | None = None) -> tuple[dict, str]:
    """Return ({"speed_kmh", "from_deg"}, source) with source forecast | reanalysis | config_default."""
    fc = cfg["forecast"]
    hour = _nearest_hour(at)
    now = dt.datetime.now(dt.UTC)
    if hour >= now - dt.timedelta(days=fc["past_days"]) and hour <= now + dt.timedelta(days=FORECAST_DAYS_AHEAD):
        url, source = fc["forecast_url"], "forecast"
    elif hour < now:
        url, source = fc["archive_url"], "reanalysis"
    else:
        return dict(cfg["weather_default"]), "config_default"   # beyond the forecast horizon

    hours = [hour + dt.timedelta(hours=k) for k in range(int(fc.get("mean_hours", 0)) + 1)]

    def cached() -> list[dict]:
        now_m = time.monotonic()
        hits = [_cache.get(_key(lat, lon, h)) for h in hours]
        return [h[1] for h in hits if h and h[0] > now_m]

    hits = cached()
    if len(hits) == len(hours):
        return mean_wind(hits), source

    params = {"latitude": lat, "longitude": lon, "hourly": "wind_speed_10m,wind_direction_10m",
              "wind_speed_unit": "kmh", "timezone": "UTC", "start_date": hour.date().isoformat(),
              "end_date": hours[-1].date().isoformat()}   # the next hours may cross midnight
    try:
        if client is None:
            async with _make_client(fc["timeout_s"]) as c:
                r = await c.get(url, params=params, timeout=fc["timeout_s"])
        else:
            r = await client.get(url, params=params, timeout=fc["timeout_s"])
        r.raise_for_status()
        hourly = r.json()["hourly"]
        expires = time.monotonic() + fc["cache_min"] * 60
        got = {}
        for t, spd, deg in zip(hourly["time"], hourly["wind_speed_10m"], hourly["wind_direction_10m"], strict=True):
            if spd is None or deg is None:
                continue
            h = dt.datetime.fromisoformat(t).replace(tzinfo=dt.UTC)
            w = {"speed_kmh": float(spd), "from_deg": float(deg)}
            _cache[_key(lat, lon, h)] = (expires, w)
            got[h] = w
        if hour not in got:
            raise ValueError(f"no wind value at {hour.isoformat()}")
        return mean_wind([got[h] for h in hours if h in got]), source   # a missing later hour is skipped
    except Exception as e:  # noqa: BLE001 - any failure falls back to the config default
        log.warning("Open-Meteo %s lookup failed (%s: %s); using weather_default", source, type(e).__name__, e)
        return dict(cfg["weather_default"]), "config_default"
