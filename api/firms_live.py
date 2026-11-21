"""Live fire map (#61): the newest VIIRS NRT detections from NASA FIRMS, every `firms_live.interval_min`.

Fetches the last `firms_live.days` days over `fire_map.bbox` (FIRMS area API, one call per source) and merges
them into `paths.detections_live` (deduplicated, rows older than `firms_live.keep_days` dropped, atomic write).
`api/detections.py` serves this file together with `paths.detections` (the archive).
Needs `FIRMS_MAP_KEY` in `.env`; without it the loop is off and `/health` says so. A failed fetch is logged
and keeps the old file.

    python -m api.firms_live        one fetch now (make firms-live)
"""
from __future__ import annotations

import asyncio
import datetime as dt
import io
import logging
import os
import sys

import httpx
import pandas as pd

from core.config import load_config, repo_path

API = "https://firms.modaps.eosdis.nasa.gov/api/area/csv"
SAT = {"VIIRS_SNPP_NRT": "SNPP", "VIIRS_NOAA20_NRT": "NOAA20", "VIIRS_NOAA21_NRT": "NOAA21"}
COLUMNS = ["lat", "lon", "t", "sat", "frp", "conf", "daynight", "country"]
log = logging.getLogger(__name__)

status: dict = {"enabled": False, "reason": "not started", "last_ok": None, "last_error": None,
                "added": 0, "newest": None}


def key() -> str:
    load_config()  # loads .env
    return os.environ.get("FIRMS_MAP_KEY", "").strip()


def parse(text: str, source: str) -> pd.DataFrame:
    """FIRMS CSV -> the step 2 columns (country left empty: api/detections.py cuts by bbox)."""
    t = text.strip()
    if not t or t.lower().startswith(("invalid", "exceeding", "error")):
        raise ValueError(f"FIRMS answered {t[:80]!r}")
    d = pd.read_csv(io.StringIO(t))
    if d.empty:
        return pd.DataFrame(columns=COLUMNS)
    missing = {"latitude", "longitude", "acq_date", "acq_time"} - set(d.columns)
    if missing:
        raise ValueError(f"FIRMS CSV lacks {sorted(missing)}")
    when = pd.to_datetime(d.acq_date + " " + d.acq_time.astype(int).astype(str).str.zfill(4),
                          format="%Y-%m-%d %H%M", utc=True)
    out = pd.DataFrame({
        "lat": d.latitude.astype(float), "lon": d.longitude.astype(float), "t": when, "sat": SAT.get(source, source),
        "frp": d.get("frp", pd.Series(float("nan"), index=d.index)).astype(float),
        "conf": d.get("confidence", pd.Series("n", index=d.index)).astype(str).str[0].str.lower(),
        "daynight": d.get("daynight", pd.Series(None, index=d.index)), "country": None})
    return out[out.conf != "l"].reset_index(drop=True)


def merge(old: pd.DataFrame | None, new: pd.DataFrame, now: pd.Timestamp, keep_days: float) -> pd.DataFrame:
    parts = [p for p in (old, new) if p is not None and len(p)]
    if not parts:
        return pd.DataFrame(columns=COLUMNS)
    d = pd.concat(parts, ignore_index=True)
    d["t"] = pd.to_datetime(d["t"], utc=True)
    d = d[d["t"] >= now - pd.Timedelta(days=keep_days)]
    k = d.lat.round(4).astype(str) + d.lon.round(4).astype(str) + d.t.dt.strftime("%Y%m%d%H%M") + d.sat.astype(str)
    return d[~k.duplicated()].sort_values("t").reset_index(drop=True)[COLUMNS]


async def fetch(cfg: dict, map_key: str, client: httpx.AsyncClient) -> pd.DataFrame:
    fl = cfg["firms_live"]
    lon_min, lat_min, lon_max, lat_max = cfg["fire_map"]["bbox"]
    area = f"{lon_min},{lat_min},{lon_max},{lat_max}"
    frames = []
    for source in fl["sources"]:
        r = await client.get(f"{API}/{map_key}/{source}/{area}/{int(fl['days'])}")
        r.raise_for_status()
        frames.append(parse(r.text, source))
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=COLUMNS)


async def run_once(cfg: dict | None = None, client: httpx.AsyncClient | None = None,
                   map_key: str | None = None) -> dict:
    """One fetch + merge + write. Updates and returns `status`; never raises on a FIRMS or network error."""
    cfg = cfg or load_config()
    map_key = key() if map_key is None else map_key
    if not map_key:
        status.update(enabled=False, reason="FIRMS_MAP_KEY is not set in .env")
        return status
    path = repo_path(cfg["paths"]["detections_live"])
    own = client is None
    client = client or httpx.AsyncClient(timeout=cfg["firms_live"]["timeout_s"])
    try:
        new = await fetch(cfg, map_key, client)
        old = pd.read_parquet(path) if path.exists() else None
        before = 0 if old is None else len(old)
        out = merge(old, new, pd.Timestamp.now(tz="UTC"), cfg["firms_live"]["keep_days"])
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".part")
        out.to_parquet(tmp, index=False)
        tmp.replace(path)
        status.update(enabled=True, reason=None, last_ok=dt.datetime.now(dt.UTC), last_error=None,
                      added=max(0, len(out) - before),
                      newest=out["t"].max().to_pydatetime() if len(out) else None)
    except (httpx.HTTPError, ValueError, OSError) as e:
        msg = str(e).replace(map_key, "<key>")
        log.warning("FIRMS live fetch failed, keeping the old file: %s", msg)
        status.update(enabled=True, reason=None, last_error=f"{dt.datetime.now(dt.UTC):%Y-%m-%d %H:%M} UTC: {msg}")
    finally:
        if own:
            await client.aclose()
    return status


async def loop(cfg: dict | None = None) -> None:
    """Background task started by api/main.py: fetch now, then every interval_min."""
    cfg = cfg or load_config()
    fl = cfg["firms_live"]
    if not fl.get("enabled", True):
        status.update(enabled=False, reason="firms_live.enabled is false in config.yaml")
        return
    if not key():
        status.update(enabled=False, reason="FIRMS_MAP_KEY is not set in .env")
        log.info("FIRMS live is off: FIRMS_MAP_KEY is not set")
        return
    while True:
        await run_once(cfg)
        await asyncio.sleep(fl["interval_min"] * 60)


def public_status() -> dict:
    return {k: (v.isoformat() if isinstance(v, dt.datetime) else v) for k, v in status.items()}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    s = asyncio.run(run_once())
    print(public_status())
    sys.exit(0 if s["enabled"] and not s["last_error"] else 1)
