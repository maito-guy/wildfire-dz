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


class AiLayer(BaseModel):
    """Model C's advice next to B (#52). Never creates flags. Only on replays for now; None elsewhere."""
    model: str                                 # e.g. "C_dza"
    label: str                                 # show it with the layer: "AI estimate (model C), check before acting"
    time: datetime                             # the satellite pass C answered for (within ai_layer.match_min)
    likely_recall: float | None                # share of burned cells C's "likely" zone catches (0.90)
    possible_recall: float | None              # same for "possible" (0.99)
    zones: dict[str, Any]                      # GeoJSON; properties.horizon_min 60 | 120, confidence likely | possible


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
    ai: AiLayer | None = None                  # model C's advice (#52); None = C has no answer for this request


class Village(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    distance_km: float                         # to the nearest burning cell
    minutes_left: int | None                   # None = not reached within the model's horizon
    ai_minutes_left: int | None = None         # model C's possible-level arrival (#52); None = no C answer within 2 h
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
    ai_minutes_left: int | None = None         # model C's view when the flag was made or updated (#52), advice only
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


# ---- today's risk layer (#28, docs/contracts.md GET /risk) -------------------------------------
RiskLevel = Literal["low", "moderate", "high", "very_high"]


class RiskCell(BaseModel):
    lat: float                                 # centre of a display cell (risk.display_cell_deg)
    lon: float
    score: float                               # 0-1, highest score among the merged 375 m cells
    level: RiskLevel


class RiskPlace(BaseModel):
    id: str
    name: str
    lat: float
    lon: float
    distance_km: float                         # to the very-high cell
    score: float
    level: RiskLevel
    top_factors: list[str]                     # e.g. ["wind", "dryness", "past fires"]
    alert_id: str                              # its preventive flag in the approval queue
    alert_status: AlertStatus


class FireWeather(BaseModel):
    date: str                                  # the day the FWI is for (= RiskResponse.date)
    source: Literal["forecast", "reanalysis"]  # Open-Meteo forecast API or ERA5 archive
    value: float                               # FWI at the worst weather point
    level: Literal["very_low", "low", "moderate", "high", "very_high", "extreme"]   # class of `value` (EFFIS)
    median: float                              # median FWI over the weather points
    points: int                                # weather points used (those nearest a risk cell)
    step_deg: float                            # weather point spacing (risk.fwi.step_deg)
    capped_cells: int                          # file cells whose level was lowered by the cap


class RiskResponse(BaseModel):
    date: str                                  # YYYY-MM-DD, the day the risk is for
    stub: bool                                 # true = fake cells, risk_today.parquet is missing
    generated_at: datetime | None              # when the risk file was written (null for the stub)
    cell_deg: float                            # display cell size in degrees (square in lat/lon)
    flag_level: RiskLevel                      # places near cells at this level are flagged
    cells: list[RiskCell]                      # levels >= risk.min_level_shown, highest score first
    places: list[RiskPlace]                    # flagged places, highest score first
    fwi: FireWeather | None = None             # the day's fire weather that capped the levels; null = no cap
    fwi_note: str | None = None                # why there is no cap (weather unavailable), else null


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
