"""FastAPI app. Contract: docs/contracts.md. Serves the dashboard at /dashboard/ and the phone alert at /alert/.

  uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import asyncio
import datetime as dt
import hmac
import itertools
import json
import logging
import os

from fastapi import Body, Depends, FastAPI, Header, HTTPException, Request
from fastapi.responses import RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from api import impact, predictor, replay, weather
from api.alerts import LANGS, Broker, store
from api.schemas import (
    Alert,
    AlertApprove,
    AlertCreate,
    AlertReject,
    AlertStatus,
    PredictRequest,
    PredictResponse,
    VillagesResponse,
)
from core.config import ROOT, load_config, repo_path

app = FastAPI(title="Wildfire early warning — northern Algeria", version="0.1.0")
FIRES: dict[str, dict] = {}          # fire_id -> latest prediction state (in memory, demo only)
_fire_ids = itertools.count(1)
log = logging.getLogger(__name__)
_dev_mode_warned = False


def require_operator(x_operator_token: str | None = Header(default=None)) -> None:
    """Write endpoints need header X-Operator-Token == env OPERATOR_TOKEN (PROGRESS D-09).

    OPERATOR_TOKEN unset or empty = dev mode: allowed, with one warning in the log.
    """
    global _dev_mode_warned
    load_config()  # loads .env once
    expected = os.environ.get("OPERATOR_TOKEN", "")
    if not expected:
        if not _dev_mode_warned:
            log.warning("OPERATOR_TOKEN is not set: write endpoints are open (dev mode)")
            _dev_mode_warned = True
        return
    if not x_operator_token or not hmac.compare_digest(x_operator_token.encode(), expected.encode()):
        raise HTTPException(401, "missing or wrong X-Operator-Token")


def _sse(request: Request, broker: Broker, keep=lambda msg: True) -> StreamingResponse:
    """Server-sent events from one broker: `hello` first, `: ping` every 15 s."""
    q = broker.subscribe()

    async def gen():
        try:
            yield "event: hello\ndata: {}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(q.get(), timeout=15)
                except TimeoutError:
                    yield ": ping\n\n"
                    continue
                if keep(msg):
                    yield msg
        finally:
            broker.unsubscribe(q)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _utc(t: dt.datetime | None) -> dt.datetime:
    if t is None:
        return dt.datetime.now(dt.UTC)
    return t if t.tzinfo else t.replace(tzinfo=dt.UTC)


@app.get("/health")
async def health():
    return {"ok": True, "fires": len(FIRES), "phones_connected": len(store.broker.queues),
            "dashboards_connected": len(store.events.queues), "pending_alerts": store.pending_count(),
            "model_c_exported": bool(predictor.manifest().get("model_c")),
            "places": "real" if impact.real_places() is not None else "stub",
            "replay": "real" if not replay.list_fires()[0]["stub"] else "stub"}


@app.post("/predict", response_model=PredictResponse)
async def predict(req: PredictRequest):
    cfg = load_config()
    try:
        lat, lon = predictor.mask_points(req.burning, req.polygon, cfg)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    if (lat < cfg["scope"]["lat_min"]).any():
        raise HTTPException(422, f"outside scope: northern Algeria only (lat >= {cfg['scope']['lat_min']})")
    time = _utc(req.time)
    observed = _utc(req.observed_at) if req.observed_at else time
    age = max(0, int((time - observed).total_seconds() // 60))
    if req.wind:
        wind, wind_src = req.wind.model_dump(), "request"
    else:  # Open-Meteo at the fire centroid; config default on any failure
        wind, wind_src = await weather.get_wind(float(lat.mean()), float(lon.mean()), time, cfg)
    model, reason, grid = predictor.run_model(req.model, lat, lon, wind["speed_kmh"], wind["from_deg"], cfg)

    fire_id = req.fire_id or f"fire_{next(_fire_ids):03d}"
    villages = impact.villages_at_risk(lat, lon, grid, cfg)
    FIRES[fire_id] = {"lat": lat, "lon": lon, "grid": grid, "time": time, "data_age_min": age,
                      "villages": villages}
    store.apply_rules(fire_id, villages, time, age)
    return PredictResponse(
        fire_id=fire_id, time=time, observed_at=observed, model=model, fallback_reason=reason,
        data_age_min=age, data_stale=age > cfg["data_age"]["stale_banner_min"], wind=wind,
        wind_source=wind_src, embers_applied=grid["embers_applied"],
        zones=predictor.zones_geojson(grid), cells=predictor.cells_list(grid),
    )


@app.get("/villages/at-risk", response_model=VillagesResponse)
async def villages_at_risk(fire_id: str | None = None):
    cfg = load_config()
    if fire_id is None and FIRES:
        fire_id = max(FIRES, key=lambda k: FIRES[k]["time"])
    f = FIRES.get(fire_id) if fire_id else None
    if f is None:
        if fire_id:
            raise HTTPException(404, f"unknown fire {fire_id}")
        return VillagesResponse(fire_id=None, time=None, data_age_min=None, data_stale=False, villages=[])
    out = []
    for v in f["villages"]:
        out.append(v | {"status": store.sticky_status(fire_id, v),
                        "last_alert_id": store.last_alert_id(fire_id, v["id"])})
    return VillagesResponse(fire_id=fire_id, time=f["time"], data_age_min=f["data_age_min"],
                            data_stale=f["data_age_min"] > cfg["data_age"]["stale_banner_min"], villages=out)


@app.get("/alerts", response_model=list[Alert])
async def list_alerts(fire_id: str | None = None, status: AlertStatus | None = None):
    return [a for a in store.alerts.values()
            if (fire_id is None or a["fire_id"] == fire_id) and (status is None or a["status"] == status)]


@app.post("/alerts", response_model=Alert, dependencies=[Depends(require_operator)])
async def send_manual(body: AlertCreate):
    fires = [body.fire_id] if body.fire_id else sorted(FIRES, key=lambda k: FIRES[k]["time"], reverse=True)
    for fid in fires:
        f = FIRES.get(fid)
        v = next((x for x in f["villages"] if x["id"] == body.village_id), None) if f else None
        if v:
            return store.send(fid, v, body.level, "manual", f["time"], f["data_age_min"])
    raise HTTPException(404, "village not found within 15 km of an active fire")


def _act(fn, alert_id: str, *args):
    try:
        return fn(alert_id, *args)
    except KeyError:
        raise HTTPException(404, f"unknown alert {alert_id}") from None
    except ValueError as e:
        raise HTTPException(409, str(e)) from None


@app.post("/alerts/{alert_id}/approve", response_model=Alert, dependencies=[Depends(require_operator)])
async def approve(alert_id: str, body: AlertApprove | None = Body(default=None)):
    body = body or AlertApprove()
    if body.texts:
        bad = sorted(set(body.texts) - set(LANGS))
        if bad:
            raise HTTPException(422, f"unknown language(s) {bad}; expected {list(LANGS)}")
        if any(not t.strip() for t in body.texts.values()):
            raise HTTPException(422, "edited texts must not be empty")
    return _act(store.approve, alert_id, body.texts, body.radius_km)


@app.post("/alerts/{alert_id}/reject", response_model=Alert, dependencies=[Depends(require_operator)])
async def reject(alert_id: str, body: AlertReject):
    return _act(store.reject, alert_id, body.reason)


@app.post("/alerts/{alert_id}/cancel", response_model=Alert, dependencies=[Depends(require_operator)])
async def cancel(alert_id: str):
    return _act(store.cancel, alert_id)


@app.get("/alerts/stream")
async def stream(request: Request, village_id: str | None = None):
    """Phones: sent alerts and cancels only. Pending or rejected flags never go here."""
    def keep(msg: str) -> bool:
        return not village_id or f'"village_id": "{village_id}"' in msg
    return _sse(request, store.broker, keep)


@app.get("/events")
async def events(request: Request):
    """Dashboards: flag, flag_updated, alert_sent, alert_rejected, alert_cancelled."""
    return _sse(request, store.events)


@app.get("/replay")
async def replay_list():
    return replay.list_fires()


@app.get("/replay/{fire_id}")
async def replay_passes(fire_id: str):
    r = replay.get_passes(fire_id)
    if r is None:
        raise HTTPException(404, f"unknown replay fire {fire_id}")
    return r


@app.get("/scoreboard")
async def scoreboard():
    p = repo_path(load_config()["paths"]["artifacts"]) / "scoreboard.json"
    if p.exists():
        return json.loads(p.read_text())
    return {"status": "not measured yet", "weather_note": "Weather is ERA5 reanalysis (a perfect forecast).",
            "fires": []}


@app.post("/reset", dependencies=[Depends(require_operator)])
async def reset():
    """Demo only: forget fires and alerts between rehearsals."""
    FIRES.clear()
    store.reset()
    return {"ok": True}


@app.get("/")
async def root():
    return RedirectResponse("/dashboard/")


app.mount("/dashboard", StaticFiles(directory=ROOT / "dashboard", html=True), name="dashboard")
app.mount("/alert", StaticFiles(directory=ROOT / "alert", html=True), name="alert")
