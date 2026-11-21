"""#61: live FIRMS detections, without the network (httpx.MockTransport)."""
import asyncio

import httpx
import pandas as pd
import pytest

from api import detections, firms_live
from core.config import load_config

CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight
36.71,4.59,330.1,0.4,0.4,2026-11-21,0112,N,VIIRS,n,2.0NRT,290.1,12.5,N
36.72,4.60,331.0,0.4,0.4,2026-11-21,0112,N,VIIRS,h,2.0NRT,291.0,30.0,N
36.73,4.61,301.0,0.4,0.4,2026-11-21,0112,N,VIIRS,l,2.0NRT,280.0,1.0,N
"""
HEADER = CSV.splitlines()[0] + "\n"


def _cfg(tmp_path):
    cfg = load_config()
    cfg["paths"]["detections_live"] = str(tmp_path / "live" / "firms_live.parquet")
    cfg["firms_live"]["keep_days"] = 100_000
    return cfg


def _client(handler):
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def test_parse_drops_low_confidence_and_maps_columns():
    d = firms_live.parse(CSV, "VIIRS_SNPP_NRT")
    assert len(d) == 2
    assert list(d.columns) == firms_live.COLUMNS
    assert set(d.sat) == {"SNPP"}
    assert d.t.iloc[0] == pd.Timestamp("2026-11-21T01:12:00Z")


@pytest.mark.parametrize("text", ["Invalid MAP_KEY.", "Exceeding allowed transaction limit."])
def test_parse_rejects_firms_errors(text):
    with pytest.raises(ValueError):
        firms_live.parse(text, "VIIRS_SNPP_NRT")


def test_run_once_writes_and_deduplicates(tmp_path):
    cfg = _cfg(tmp_path)
    calls = []

    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(200, text=CSV if "SNPP" in req.url.path else HEADER)

    async def go():
        async with _client(handler) as c:
            await firms_live.run_once(cfg, client=c, map_key="k")
            return await firms_live.run_once(cfg, client=c, map_key="k")

    s = asyncio.run(go())
    assert len(calls) == 2 * len(cfg["firms_live"]["sources"])
    assert all("/k/" in p and "/-2.3,34.5,8.7,37.2/" in p for p in calls)
    out = pd.read_parquet(tmp_path / "live" / "firms_live.parquet")
    assert len(out) == 2                      # second run adds nothing
    assert s["last_error"] is None and s["added"] == 0 and s["enabled"]


def test_failure_keeps_old_file_and_hides_key(tmp_path):
    cfg = _cfg(tmp_path)

    async def go(handler):
        async with _client(handler) as c:
            return await firms_live.run_once(cfg, client=c, map_key="secret123")

    asyncio.run(go(lambda req: httpx.Response(200, text=CSV)))
    s = asyncio.run(go(lambda req: httpx.Response(503, text="down")))
    assert s["last_error"] and "secret123" not in s["last_error"]
    assert len(pd.read_parquet(tmp_path / "live" / "firms_live.parquet")) == 2 * len(cfg["firms_live"]["sources"])


def test_no_key_is_off(tmp_path):
    s = asyncio.run(firms_live.run_once(_cfg(tmp_path), map_key=""))
    assert s["enabled"] is False and "FIRMS_MAP_KEY" in s["reason"]


def test_merge_drops_old_rows():
    now = pd.Timestamp("2026-11-21T12:00:00Z")
    d = firms_live.parse(CSV, "VIIRS_SNPP_NRT")
    old = d.assign(t=now - pd.Timedelta(days=30))
    assert len(firms_live.merge(old, d, now, keep_days=14)) == 2


def test_detections_serve_archive_plus_live(tmp_path, monkeypatch):
    archive = pd.DataFrame({"lat": [36.5], "lon": [5.0], "t": [pd.Timestamp("2026-09-08T12:49Z")], "sat": ["SNPP"],
                            "frp": [5.0], "conf": ["n"], "daynight": ["D"], "country": ["DZA"]})
    a, live = tmp_path / "det.parquet", tmp_path / "live.parquet"
    archive.to_parquet(a)
    d = firms_live.parse(CSV, "VIIRS_SNPP_NRT")
    # one live row outside the bbox (Tunisia) is cut; one duplicates the archive
    extra = d.iloc[:1].assign(lon=9.5)
    dup = archive.assign(country=None)
    pd.concat([d, extra, dup], ignore_index=True).to_parquet(live)
    cfg = load_config()
    cfg["paths"]["detections"], cfg["paths"]["detections_live"] = str(a), str(live)
    monkeypatch.setattr(detections, "load_config", lambda: cfg)
    df = detections.real_detections()
    assert len(df) == 3
    assert df.t.max() == pd.Timestamp("2026-11-21T01:12:00Z")
    r = detections.detections()
    assert r["stub"] is False and r["newest"].isoformat().startswith("2026-11-21")
