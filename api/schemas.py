"""API contract as Pydantic models. Mirrors docs/contracts.md — change both together, with a note to the team."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

Status = Literal["safe", "get_ready", "leave_now"]
AlertLevel = Literal["get_ready", "leave_now", "update", "preventive"]
AlertStatus = Literal["pending", "sent", "rejected", "cancelled"]
AlertSource = Literal["ai_spread", "ai_risk", "manual"]


class LatLon(BaseModel):
    lat: float
    lon: float


class Wind(BaseModel):
    speed_kmh: float = Field(ge=0)
    from_deg: float = Field(ge=0, lt=360)


class PredictRequest(BaseModel):
    fire_id: str | None = None                 # omit to create a new fire ("start a fire here")
    time: datetime | None = None               # scenario clock; default = now (UTC)
    observed_at: datetime | None = None        # satellite pass time of this mask; default = time
    burning: list[LatLon] | None = None        # burning cells as points ...
    polygon: dict[str, Any] | None = None      # ... or a GeoJSON Polygon / MultiPolygon
    model: Literal["auto", "A", "B", "C"] = "auto"
    wind: Wind | None = None                   # override; default = forecast (P1) or config default


class Cell(BaseModel):
    lat: float
    lon: float
    arrival_min: float


class PredictResponse(BaseModel):
    fire_id: str
    time: datetime
    observed_at: datetime
    model: Literal["A", "B", "C"]
    fallback_reason: str | None = None
    data_age_min: int
    data_stale: bool
    wind: Wind
    wind_source: Literal["request", "forecast", "reanalysis", "config_default"]
    embers_applied: bool
    zones: dict[str, Any]                      # GeoJSON FeatureCollection, properties.horizon_min = 60 | 120
    cells: list[Cell]                          # every cell reached within 120 min


class Village(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    distance_km: float                         # to the nearest burning cell
    minutes_left: int | None                   # None = not reached within the model's horizon
    status: Status                             # sticky: never back to "safe" while the fire is active
    fire_direction: str                        # compass direction of the fire, seen from the village
    leave_toward: str                          # compass direction to leave toward
    leave_toward_deg: float
    last_alert_id: str | None = None


class VillagesResponse(BaseModel):
    fire_id: str | None
    time: datetime | None
    data_age_min: int | None
    data_stale: bool
    villages: list[Village]                    # sorted by minutes_left, most urgent first


class AlertArea(BaseModel):
    lat: float
    lon: float
    radius_km: float


class Alert(BaseModel):
    id: str
    fire_id: str
    village_id: str
    village_name: str
    level: AlertLevel
    source: AlertSource                        # ai_spread = /predict rule, ai_risk = risk job, manual = operator
    status: AlertStatus                        # pending -> sent | rejected; sent -> cancelled
    created_at: datetime                       # wall clock (flagged, or sent for manual alerts)
    scenario_time: datetime                    # fire clock (replay time)
    approved_at: datetime | None = None        # operator approved (or sent a manual alert)
    rejected_at: datetime | None = None
    reject_reason: str | None = None
    cancelled_at: datetime | None = None
    edited: bool = False                       # operator changed the texts before approving
    minutes_left: int | None
    distance_km: float
    fire_direction: str
    leave_toward: str
    data_age_min: int
    area: AlertArea
    texts: dict[str, str]                      # language code -> rendered text (en, fr, ar, ary, kab)


class AlertCreate(BaseModel):
    village_id: str
    fire_id: str | None = None                 # default: the fire nearest the village
    level: AlertLevel = "leave_now"


class AlertApprove(BaseModel):
    texts: dict[str, str] | None = None        # language code -> replacement text (sets edited = true)
    radius_km: float | None = Field(default=None, gt=0, le=50)


class AlertReject(BaseModel):
    reason: str = Field(min_length=1)


# --- Fire map (#29): GET /detections, GET /history ---------------------------------------------------
class Detection(BaseModel):
    lat: float
    lon: float
    t: datetime                                # acquisition time (UTC)
    satellite: str | None = None               # SNPP | NOAA20 | NOAA21
    frp: float | None = None                   # fire radiative power, MW
    confidence: str | None = None              # n (nominal) | h (high); low-confidence rows are dropped upstream
    daynight: str | None = None                # D | N


class DetectionsResponse(BaseModel):
    stub: bool                                 # true = synthetic detections, not real data
    newest: datetime | None                    # newest detection in the data; the "last 24 h / 7 days" clock
    since: datetime
    until: datetime
    count: int
    truncated: bool                            # more matched than fire_map.max_points (the newest are kept)
    detections: list[Detection]                # newest first


class HistoryCell(BaseModel):
    lat: float                                 # cell centre
    lon: float
    count: int                                 # detections in the cell, all years
    years: int | None = None                   # distinct years with a detection
    last_year: int | None = None


class HistoryResponse(BaseModel):
    stub: bool
    source: Literal["grid", "detections", "stub"]   # history_grid.parquet, aggregated detections, or stub
    cell_deg: float                            # cell size in degrees (lat and lon)
    first_year: int | None
    last_year: int | None
    max_count: int
    cells: list[HistoryCell]
