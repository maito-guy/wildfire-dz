# Contracts (frozen)

Source: `2-project-context.md` §7. Change these **only** with a PR that updates this file, `api/schemas.py`
and a message in the team chat naming who is affected. Everything is WGS84 lat/lon, and times are ISO 8601 UTC.

## Changelog
- **v0.1 (Fri 20 Nov, 08:45).** First full write-up of §7. Additions needed by the screens, all read-only or demo-only:
  `GET /health`, `GET /alerts`, `GET /replay`, `GET /replay/{fire_id}`, `GET /scoreboard`, `POST /reset`.
  Nothing in §7 changed.

---

## 1. Data contract

### Grid
375 m cells on each fire's local equirectangular grid (`lat0, lon0, mlon` in `fires.parquet`):
`x = (lon − lon0)·π/180·R·cos(lat0)`, `y = (lat − lat0)·π/180·R`, with R = 6,371 km (`core/geo.py`).

### `data/out/train.parquet`: produced by `data/05_build_table.py`, read by `model/`
One row per **candidate cell** (within 3 km of the fire) per **pass pair**. `label = 1` means the cell is burning at the next pass.
30% of negatives are kept, and `weight` undoes that sampling (weighted metrics count negatives correctly).

| Group | Columns |
|---|---|
| Geometry | `dist_burned_m, dist_active_m, downwind_cos, uphill_grade, n_active, n_burned, frp_active_sum, frp_nearest, hour_local, gap_min, kind` (`short` = 20–120 min, `long` = 2–16 h) |
| Terrain | `elev, elev_std, slope, aspect_sin, aspect_cos` |
| Fuel shares | `tree, shrub, grass, crop, built, bare, water` |
| Weather (ERA5) | temperature, RH, VPD, wind speed/gusts now, wind over next 2 h (speed, from-direction), max gust, soil moisture, hours since rain, rain last 24 h |
| IDs | `fire_id, country, t1, ix, iy, lat, lon` |
| Target | `label, weight` |

Exact weather column names come from `05_build_table.py`. `make check-columns` prints them, and `config.yaml → columns` maps the ones the code uses.
**Label caveat:** no detection ≠ no fire (cloud, smoke, viewing angle).

### Holdouts: whole fires, never random rows
A fire is held out if any of its rows falls inside the window **and** bbox (`config.yaml → holdouts`; UI/UX 1 confirms by eye):
- `kabylie_2021`: 5–16 Aug 2021 (also the replay fire)
- `jijel_guelma_2026`: 26 Aug – 8 Sep 2026

### `data/out/places.parquet` → `api/impact.py`
`id (str), name (str), lat, lon` (+ optional `name_ar`). Source: 10,258 OSM settlements from the export.

### `data/out/replay_passes.parquet` → `api/replay.py`
One row per burning cell per pass: `holdout (str: kabylie_2021 | jijel_guelma_2026), t (UTC timestamp), lat, lon` (+ optional `satellite, frp`).

### `model/artifacts/` → API (git-ignored; share via Drive)
| File | Writer | Content |
|---|---|---|
| `model_c_<tag>.txt`, `features_<tag>.json` | `model.train` | LightGBM booster + feature list (`tag` = `mixed` or `dza`) |
| `thresholds.json` | `model.evaluate` | tuned `rate_m_per_min` for A and B, `prob` threshold per C |
| `scoreboard.json` | `model.evaluate` | per holdout × model metrics (shape in §2, `GET /scoreboard`) |
| `api_manifest.json` | `model.export` | what the API loads: rates for A/B and the shipped C (or `null`) |

---

## 2. API contract

Base URL: `http://<laptop-ip>:8000`. The dashboard is at `/dashboard/` and the phone page at `/alert/` (same origin, no CORS).

### Status rules (from config, kept on purpose)
| minutes_left | status |
|---|---|
| > 120, `null`, or no zone within 15 km | `safe` |
| 60–120 | `get_ready` |
| < 60 | `leave_now` |

Status is **sticky**: a warned village never goes back to `safe` while the fire is active.

### `POST /predict`
Takes the current fire mask and a time. Returns the 1 h / 2 h zones, per-cell arrival times, the model used and the data age.
It also stores the fire and runs the auto-alert rule. "Start a fire here" = this call with one point and no `fire_id`.

Request:
```json
{
  "fire_id": "kabylie_2021",
  "time": "2021-08-09T12:00:00Z",
  "observed_at": "2021-08-09T11:13:00Z",
  "burning": [{"lat": 36.65, "lon": 4.10}, {"lat": 36.652, "lon": 4.104}],
  "polygon": null,
  "model": "auto",
  "wind": {"speed_kmh": 45, "from_deg": 270}
}
```
- `burning` **or** `polygon` (GeoJSON Polygon/MultiPolygon, sampled at 375 m).
- `fire_id` omitted → a new id is created. `time` omitted → now. `observed_at` omitted → `time`.
- `model`: `auto | A | B | C`. `auto` = C when shipped and wired, else B. **Fail-safe:** if C errors → B and `fallback_reason` says why.
- `wind` omitted → Open-Meteo hourly 10 m wind at the fire centroid, at the hour nearest `time` (UTC; 3 s timeout, cached 15 min): `time` within `now - forecast.past_days` … `now + 7 days` → forecast API (`wind_source: "forecast"`); older → archive API, ERA5 (`"reanalysis"`); any error, timeout or missing value → `config.yaml → weather_default` (`"config_default"`). A request `wind` always wins (`"request"`).
- `wind_source`: `request | forecast | reanalysis | config_default`.
- 422 if a point is south of 34.5°N.

Response 200:
```json
{
  "fire_id": "fire_001",
  "time": "2021-08-09T12:00:00Z",
  "observed_at": "2021-08-09T11:13:00Z",
  "model": "B",
  "fallback_reason": null,
  "data_age_min": 47,
  "data_stale": false,
  "wind": {"speed_kmh": 45.0, "from_deg": 270.0},
  "wind_source": "request",
  "embers_applied": true,
  "zones": {
    "type": "FeatureCollection",
    "features": [
      {"type": "Feature", "properties": {"horizon_min": 60},
       "geometry": {"type": "Polygon", "coordinates": [[[4.1083, 36.6392], [4.1041, 36.6392], [4.1041, 36.6459], "..."]]}},
      {"type": "Feature", "properties": {"horizon_min": 120},
       "geometry": {"type": "Polygon", "coordinates": [[[4.1041, 36.6392], [4.0999, 36.6392], [4.0999, 36.6628], "..."]]}}
    ]
  },
  "cells": [
    {"lat": 36.61053, "lon": 4.15244, "arrival_min": 118.8},
    {"lat": 36.61053, "lon": 4.15665, "arrival_min": 116.2}
  ]
}
```
`data_stale` = `data_age_min > 180` → the screens show the banner. `embers_applied` = wind > 40 km/h → zone widened one ring downwind.

### `GET /villages/at-risk?fire_id=<id>`
Each place within 15 km of the fire, most urgent first. If `fire_id` is omitted, the most recently updated fire is used.
```json
{
  "fire_id": "fire_001",
  "time": "2021-08-09T12:00:00Z",
  "data_age_min": 47,
  "data_stale": false,
  "villages": [
    {
      "id": "osm:123456",
      "name": "Village X",
      "lat": 36.66, "lon": 4.11,
      "distance_km": 1.04,
      "minutes_left": 31,
      "status": "leave_now",
      "fire_direction": "SW",
      "leave_toward": "NE",
      "leave_toward_deg": 31.0,
      "last_alert_id": "al_0001"
    }
  ]
}
```
`minutes_left: null` = not reached within the model's horizon. `leave_toward` = away from the nearest burning cell (no road routing).

### Alert object (used by every alert endpoint and the stream)
```json
{
  "id": "al_0001",
  "fire_id": "fire_001",
  "village_id": "osm:123456",
  "village_name": "Village X",
  "level": "leave_now",
  "source": "auto",
  "status": "sent",
  "created_at": "2026-11-20T07:37:33Z",
  "scenario_time": "2021-08-09T12:00:00Z",
  "cancelled_at": null,
  "minutes_left": 31,
  "distance_km": 1.04,
  "fire_direction": "SW",
  "leave_toward": "NE",
  "data_age_min": 47,
  "area": {"lat": 36.66, "lon": 4.11, "radius_km": 5.0},
  "texts": {
    "en": "Village X: LEAVE NOW toward the NE. Fire expected in about 31 minutes. Take water, ID and medicine. Call Civil Protection: [number, to confirm]."
  }
}
```
`level`: `get_ready | leave_now | update`. `source`: `auto | manual`. `status`: `sent | cancelled`.
`texts` keys: `ary` (Darija), `kab` (Kabyle), `ar`, `fr`, `en`. A language appears only once its checked text exists in `alert/texts.json`.

**Auto rule** (runs on every `/predict`): a village crossing into `get_ready`/`leave_now` gets an alert at that level. Escalation sends again, and the same level is never re-sent.
If a warned village's computed status falls to `safe`, it gets one `update` alert.

### `POST /alerts`: manual extra alert
```json
{"village_id": "osm:123456", "fire_id": "fire_001", "level": "leave_now"}
```
→ 200 Alert object (`source: "manual"`). 404 if the village is not within 15 km of an active fire.

### `POST /alerts/{id}/cancel`
No body → 200 Alert object with `status: "cancelled"`, `cancelled_at` set. It pushes a `cancel` event to the phones.
It does not re-arm auto-send at that level for that village. 404 if the id is unknown.

### `GET /alerts?fire_id=<id>` *(added v0.1)*
→ `[Alert, ...]` in send order.

### `GET /alerts/stream?village_id=<id>`: push stream (SSE)
`text/event-stream`. Events:
```
event: hello
data: {}

event: alert
data: {Alert object}

event: cancel
data: {Alert object, status "cancelled"}

: ping            (every 15 s keep-alive)
```
`village_id` omitted = every alert (demo default, like phones in the whole area). Browsers reconnect automatically.

### `GET /replay` *(added v0.1)*
```json
[{"fire_id": "stub_synthetic", "name": "STUB synthetic fire (not real data)", "n_passes": 8, "stub": true}]
```
That is the stub answer. Once `replay_passes.parquet` exists, there is one entry per holdout (`fire_id` = holdout key, `stub: false`).

### `GET /replay/{fire_id}` *(added v0.1)*
```json
{
  "fire_id": "stub_synthetic",
  "name": "STUB synthetic fire (not real data)",
  "stub": true,
  "passes": [
    {"t": "2021-08-09T01:30:00+00:00", "satellite": "NOAA-20",
     "burning": [{"lat": 36.64911, "lon": 4.10071}, {"lat": 36.64935, "lon": 4.10463}]}
  ]
}
```
The dashboard posts each pass to `/predict` (`time = observed_at = t`) and draws the **next** pass as "what really burned".

### `GET /scoreboard` *(added v0.1)*
Serves `model/artifacts/scoreboard.json`. Before the first evaluation it returns `{"status": "not measured yet", ...}`.
```json
{
  "generated_at": "2026-11-20T21:00:00+00:00",
  "weather_note": "Training and evaluation weather is ERA5 reanalysis, i.e. a perfect forecast. Live accuracy will be lower.",
  "horizon": "1h, pairs 20-120 min apart",
  "thresholds": {"target_recall": 0.95, "A": {"rate_m_per_min": null}, "B": {"rate_m_per_min": null}, "C_mixed": {"prob": null}},
  "fires": [
    {"holdout": "kabylie_2021", "name": "Kabylie, 5-16 Aug 2021", "n_fires": null,
     "models": {
       "A": {"recall_1h": null, "false_alarm_cell_share": null, "zone_cells_per_burned_cell": null,
             "missed_villages": null, "median_lead_min": null, "false_alarm_villages": null, "status": "not measured yet"},
       "B": {"...": "same keys"},
       "C_mixed": {"...": "same keys"},
       "C_dza": {"...": "same keys"}
     }}
  ],
  "ship_c": {"rule": "C ships only if it beats B on missed villages and lead time", "decision": "not measured yet"}
}
```
(All values are `null` here on purpose. Real numbers come only from `model.evaluate`.)

### `GET /health` *(added v0.1)*
```json
{"ok": true, "fires": 1, "phones_connected": 4, "model_c_exported": false, "places": "real", "replay": "real"}
```
`places`/`replay` = `stub` until the data files exist. Check `phones_connected` before each demo run.

### `POST /reset` *(added v0.1, demo only)*
Clears fires and alerts between rehearsals → `{"ok": true}`.
