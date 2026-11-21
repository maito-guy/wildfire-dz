"""The day's fire weather (Canadian Fire Weather Index, the index EFFIS uses) to cap the risk levels (#57).

The risk file (D-15: the Algeria Fire Map export) ranks cells against each other, so it is as red in January as
on a sirocco day. The FWI measures the day's weather danger in absolute terms; `api/risk.py` caps each cell's
level by the FWI class of its nearest weather point (`config.yaml -> risk.fwi.cap`).

Weather: Open-Meteo daily values on a coarse grid (`risk.fwi.step_deg`, only the points nearest a risk cell),
in ONE batched request: the forecast API when the whole spin-up window is within `forecast_max_past_days`
days of today, else the ERA5 archive. The FWI codes start from the standard values (FFMC 85, DMC 6, DC 15)
`spinup_days` days before the date. Noon values are approximated by the day's max temperature, min humidity,
mean wind (noon wind sits between the mean and the max) and total rain: a slightly high FWI, so the cap errs toward
showing danger.
Successful answers are cached per (date, points) for `cache_min` minutes; failures are not cached and return
None, and then the levels are not capped (a failed weather call never hides a real danger).

Equations: Van Wagner (1987), "Development and structure of the Canadian Forest Fire Weather Index System",
Canadian Forestry Service, Forestry Technical Report 35, written here from the published equations (standard
day-length factors for the northern mid-latitudes, which cover northern Algeria).
"""
from __future__ import annotations

import datetime as dt
import logging
import time

import httpx
import numpy as np

log = logging.getLogger(__name__)

DAILY = "temperature_2m_max,relative_humidity_2m_min,wind_speed_10m_mean,precipitation_sum"
START_FFMC, START_DMC, START_DC = 85.0, 6.0, 15.0
# Day-length factors by month, Van Wagner (1987) tables for ~46 deg N (cffdrs uses them for lat > 33 / > 20).
DMC_LE = np.array([6.5, 7.5, 9.0, 12.8, 13.9, 13.9, 12.4, 10.9, 9.4, 8.0, 7.0, 6.0])
DC_LF = np.array([-1.6, -1.6, -1.6, 0.9, 3.8, 5.8, 6.4, 5.0, 2.4, 0.4, -1.6, -1.6])

_cache: dict[tuple, tuple[float, dict]] = {}   # key -> (expires monotonic, result)


# ---------- the FWI system (vectorised over points) ----------
def ffmc(t, h, w, rain, f0):
    """Fine Fuel Moisture Code. t deg C, h % RH, w km/h, rain mm/24 h, f0 yesterday's FFMC."""
    t, h, w, rain, f0 = (np.asarray(x, dtype=float) for x in (t, h, w, rain, f0))
    mo = 147.2 * (101.0 - f0) / (59.5 + f0)
    rf = np.maximum(rain - 0.5, 1e-9)
    wet = rain > 0.5
    add = 42.5 * rf * np.exp(-100.0 / (251.0 - mo)) * (1.0 - np.exp(-6.93 / rf))
    add = add + np.where(mo > 150.0, 0.0015 * (mo - 150.0) ** 2 * np.sqrt(rf), 0.0)
    mo = np.where(wet, np.minimum(mo + add, 250.0), mo)
    ed = 0.942 * h ** 0.679 + 11.0 * np.exp((h - 100.0) / 10.0) + 0.18 * (21.1 - t) * (1.0 - np.exp(-0.115 * h))
    ew = 0.618 * h ** 0.753 + 10.0 * np.exp((h - 100.0) / 10.0) + 0.18 * (21.1 - t) * (1.0 - np.exp(-0.115 * h))
    ko = 0.424 * (1.0 - (h / 100.0) ** 1.7) + 0.0694 * np.sqrt(w) * (1.0 - (h / 100.0) ** 8)
    kd = ko * 0.581 * np.exp(0.0365 * t)
    k1 = 0.424 * (1.0 - ((100.0 - h) / 100.0) ** 1.7) + 0.0694 * np.sqrt(w) * (1.0 - ((100.0 - h) / 100.0) ** 8)
    kw = k1 * 0.581 * np.exp(0.0365 * t)
    m = np.where(mo > ed, ed + (mo - ed) * 10.0 ** (-kd), np.where(mo < ew, ew - (ew - mo) * 10.0 ** (-kw), mo))
    return np.clip(59.5 * (250.0 - m) / (147.2 + m), 0.0, 101.0)


def dmc(t, h, rain, p0, month):
    """Duff Moisture Code. month 1-12."""
    t, h, rain, p0 = (np.asarray(x, dtype=float) for x in (t, h, rain, p0))
    t = np.maximum(t, -1.1)
    k = 1.894 * (t + 1.1) * (100.0 - h) * DMC_LE[month - 1] * 1e-6
    re = 0.92 * rain - 1.27
    mo = 20.0 + np.exp(5.6348 - p0 / 43.43)
    with np.errstate(divide="ignore", invalid="ignore"):
        lp = np.log(np.maximum(p0, 1e-9))
        b = np.where(p0 <= 33.0, 100.0 / (0.5 + 0.3 * p0), np.where(p0 <= 65.0, 14.0 - 1.3 * lp, 6.2 * lp - 17.2))
        mr = mo + 1000.0 * re / (48.77 + b * re)
        pr = np.maximum(244.72 - 43.43 * np.log(np.maximum(mr - 20.0, 1e-9)), 0.0)
    p = np.where(rain > 1.5, pr, p0)
    return np.maximum(p + 100.0 * k, 0.0)


def dc(t, rain, d0, month):
    """Drought Code. month 1-12."""
    t, rain, d0 = (np.asarray(x, dtype=float) for x in (t, rain, d0))
    t = np.maximum(t, -2.8)
    pe = np.maximum((0.36 * (t + 2.8) + DC_LF[month - 1]) / 2.0, 0.0)
    rd = 0.83 * rain - 1.27
    qr = 800.0 * np.exp(-d0 / 400.0) + 3.937 * rd
    with np.errstate(divide="ignore", invalid="ignore"):
        dr = np.maximum(400.0 * np.log(800.0 / np.maximum(qr, 1e-9)), 0.0)
    return np.where(rain > 2.8, dr, d0) + pe


def isi(w, f):
    """Initial Spread Index from wind (km/h) and today's FFMC."""
    w, f = np.asarray(w, dtype=float), np.asarray(f, dtype=float)
    fm = 147.2 * (101.0 - f) / (59.5 + f)
    sf = 19.115 * np.exp(-0.1386 * fm) * (1.0 + fm ** 5.31 / 4.93e7)
    return sf * np.exp(0.05039 * w)


def bui(p, d):
    """Buildup Index from today's DMC and DC."""
    p, d = np.asarray(p, dtype=float), np.asarray(d, dtype=float)
    with np.errstate(divide="ignore", invalid="ignore"):
        low = 0.8 * p * d / (p + 0.4 * d)
        high = p - (1.0 - 0.8 * d / (p + 0.4 * d)) * (0.92 + (0.0114 * p) ** 1.7)
    u = np.where(p <= 0.4 * d, low, high)
    return np.maximum(np.nan_to_num(u, nan=0.0), 0.0)


def fwi(i, u):
    """Fire Weather Index from ISI and BUI."""
    i, u = np.asarray(i, dtype=float), np.asarray(u, dtype=float)
    fd = np.where(u <= 80.0, 0.626 * u ** 0.809 + 2.0, 1000.0 / (25.0 + 108.64 * np.exp(-0.023 * u)))
    b = 0.1 * i * fd
    with np.errstate(divide="ignore", invalid="ignore"):
        s = np.exp(2.72 * (0.434 * np.log(np.maximum(b, 1e-9))) ** 0.647)
    return np.where(b > 1.0, s, b)


def run(days: list[dt.date], t, h, w, rain) -> np.ndarray:
    """FWI on the last day after running the codes over every day. t/h/w/rain: arrays (days, points).
    A missing value (NaN) on a day leaves that point's codes unchanged that day; NaN on the last day -> NaN."""
    t, h, w, rain = (np.asarray(x, dtype=float) for x in (t, h, w, rain))
    n = t.shape[1]
    f, p, d = np.full(n, START_FFMC), np.full(n, START_DMC), np.full(n, START_DC)
    out = np.full(n, np.nan)
    for k, day in enumerate(days):
        ok = ~(np.isnan(t[k]) | np.isnan(h[k]) | np.isnan(w[k]) | np.isnan(rain[k]))
        hk = np.clip(np.nan_to_num(h[k], nan=50.0), 0.0, 100.0)
        tk, wk, rk = np.nan_to_num(t[k]), np.nan_to_num(w[k]), np.nan_to_num(rain[k])
        f2, p2, d2 = ffmc(tk, hk, wk, rk, f), dmc(tk, hk, rk, p, day.month), dc(tk, rk, d, day.month)
        f, p, d = np.where(ok, f2, f), np.where(ok, p2, p), np.where(ok, d2, d)
        out = np.where(ok, fwi(isi(wk, f), bui(p, d)), np.nan)
    return out


def classify(value: float, classes: dict) -> str:
    """FWI value -> class name, from `risk.fwi.classes` (lower bounds, ascending)."""
    name = "very_low"
    for c, lower in sorted(classes.items(), key=lambda kv: kv[1]):
        if value >= lower:
            name = c
    return name


# ---------- weather points and Open-Meteo ----------
def grid(cfg: dict) -> tuple[np.ndarray, np.ndarray]:
    """Weather point lat, lon over fire_map.bbox at risk.fwi.step_deg (flattened)."""
    step = float(cfg["risk"]["fwi"]["step_deg"])
    lon_min, lat_min, lon_max, lat_max = cfg["fire_map"]["bbox"]
    la = np.arange(lat_min, lat_max + 1e-9, step)
    lo = np.arange(lon_min, lon_max + 1e-9, step)
    la2, lo2 = np.meshgrid(la, lo, indexing="ij")
    return np.round(la2.ravel(), 4), np.round(lo2.ravel(), 4)


def nearest(cfg: dict, lat, lon) -> np.ndarray:
    """Index of the nearest weather point for each (lat, lon)."""
    step = float(cfg["risk"]["fwi"]["step_deg"])
    lon_min, lat_min, lon_max, lat_max = cfg["fire_map"]["bbox"]
    n_lat = len(np.arange(lat_min, lat_max + 1e-9, step))
    n_lon = len(np.arange(lon_min, lon_max + 1e-9, step))
    i = np.clip(np.round((np.asarray(lat, dtype=float) - lat_min) / step).astype(int), 0, n_lat - 1)
    j = np.clip(np.round((np.asarray(lon, dtype=float) - lon_min) / step).astype(int), 0, n_lon - 1)
    return i * n_lon + j


def _make_client(timeout_s: float) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=timeout_s)


def _url(cfg: dict, start: dt.date, today: dt.date) -> tuple[str, str]:
    fc, fw = cfg["forecast"], cfg["risk"]["fwi"]
    if (today - start).days <= fw["forecast_max_past_days"]:
        return fc["forecast_url"], "forecast"
    return fc["archive_url"], "reanalysis"


async def for_day(date: str, cfg: dict, points: np.ndarray,
                  client: httpx.AsyncClient | None = None) -> dict | None:
    """FWI per weather point for `date` (YYYY-MM-DD). points: indices into grid(cfg).
    Returns {"date", "source", "step_deg", "points": {index: fwi}} or None on any failure."""
    fw = cfg["risk"]["fwi"]
    if not fw.get("enabled", True) or len(points) == 0:
        return None
    points = np.unique(np.asarray(points, dtype=int))
    key = (date, float(fw["step_deg"]), tuple(cfg["fire_map"]["bbox"]), tuple(points.tolist()))
    hit = _cache.get(key)
    if hit and hit[0] > time.monotonic():
        return hit[1]
    day = dt.date.fromisoformat(date)
    start = day - dt.timedelta(days=int(fw["spinup_days"]))
    url, source = _url(cfg, start, dt.datetime.now(dt.UTC).date())
    la, lo = grid(cfg)
    params = {"latitude": ",".join(f"{x:g}" for x in la[points]),
              "longitude": ",".join(f"{x:g}" for x in lo[points]),
              "daily": DAILY, "wind_speed_unit": "kmh", "timezone": "UTC",
              "start_date": start.isoformat(), "end_date": day.isoformat()}
    try:
        if client is None:
            async with _make_client(fw["timeout_s"]) as c:
                r = await c.get(url, params=params, timeout=fw["timeout_s"])
        else:
            r = await client.get(url, params=params, timeout=fw["timeout_s"])
        r.raise_for_status()
        body = r.json()
        results = body if isinstance(body, list) else [body]
        if len(results) != len(points):
            raise ValueError(f"{len(results)} locations answered, {len(points)} asked")
        days = [dt.date.fromisoformat(x[:10]) for x in results[0]["daily"]["time"]]
        if not days or days[-1] != day:
            raise ValueError(f"weather ends on {days[-1] if days else 'nothing'}, not {date}")

        def col(name):
            return np.array([[np.nan if v is None else v for v in res["daily"][name]] for res in results],
                            dtype=float).T

        values = run(days, col("temperature_2m_max"), col("relative_humidity_2m_min"),
                     col("wind_speed_10m_mean"), col("precipitation_sum"))
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as e:
        why = f"HTTP {e.response.status_code}" if isinstance(e, httpx.HTTPStatusError) else f"{type(e).__name__}: {e}"
        log.warning("fire weather for %s unavailable (%s): risk levels are not capped", date, why[:200])
        return None
    out = {"date": date, "source": source, "step_deg": float(fw["step_deg"]),
           "points": {int(p): float(v) for p, v in zip(points, values) if np.isfinite(v)}}
    if not out["points"]:
        log.warning("fire weather for %s has no values: risk levels are not capped", date)
        return None
    _cache[key] = (time.monotonic() + 60 * float(fw["cache_min"]), out)
    return out
