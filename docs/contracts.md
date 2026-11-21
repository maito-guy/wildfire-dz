# Contracts (frozen)

Source: `2-project-context.md` §7. Change these **only** with a PR that updates this file, `api/schemas.py`
and a message in the team chat naming who is affected. Everything is WGS84 lat/lon, and times are ISO 8601 UTC.

## Changelog
- **v0.1 (Fri 20 Nov, 08:45).** First full write-up of §7. Additions needed by the screens, all read-only or demo-only:
  `GET /health`, `GET /alerts`, `GET /replay`, `GET /replay/{fire_id}`, `GET /scoreboard`, `POST /reset`.
  Nothing in §7 changed.
- **v0.2 (#24, approval queue).** Nothing reaches the phones without an operator click. Alert gains `status`
  `pending | rejected`, level `preventive`, `source` `ai_spread | ai_risk | manual` (replaces `auto`), and
  `approved_at`, `rejected_at`, `reject_reason`, `edited`. New: `POST /alerts/{id}/approve`, `POST /alerts/{id}/reject`,
  `GET /events`, `GET /alerts?status=`. Write endpoints take `X-Operator-Token`. `/health` adds
  `dashboards_connected` and `pending_alerts`. Affected: dashboard (queue), phone page (unchanged shape), CAP (#26), risk flags (#28).
- **v0.3 (#26, CAP message).** New `GET /alerts/{id}/cap.xml` (CAP 1.2, Alert or Cancel) and the simulated
  cell-broadcast hand-off log line. New `config.yaml` section `cap:`. Alert object unchanged. Affected: dashboard (link to the XML).
- **#21 (scoreboard view).** `GET /scoreboard` without `scoreboard.json` now serves a stub of the full shape,
  flagged `stub: true`, every metric `null` (was `{"status", "weather_note", "fires": []}`). New optional
  `replay_counter` (the "warned X before vs old method" counter). Additive; affected: dashboard, `model.evaluate` (#19).
- **v0.4 (#28, risk layer).** New file `model/artifacts/risk_today.parquet` (written by `model.risk`, #27; read by
  `api/risk.py`) and new `GET /risk`. Until the file exists, `/risk` serves deterministic stub cells (`stub: true`).
  Very-high-risk places become pending `preventive` flags (`source: ai_risk`, `fire_id: risk_<date>`), one per place
  and day. New `config.yaml` keys `paths.risk_today` and section `risk:`. Alert object unchanged.
  Affected: AI (#27 writes the file), dashboard (risk layer, queue).

- **v0.5 (#29, fire map).** New files `data/out/detections.parquet` and `data/out/history_grid.parquet` (Data writes
  them; read by `api/detections.py`) and new `GET /detections` and `GET /history`. Until the files exist both serve
  deterministic stub data (`stub: true`). New `config.yaml` keys `paths.detections`, `paths.history_grid` and section
  `fire_map:`. Affected: Data (writes the files), dashboard (fire map layers).

- **v0.6 (#52, AI layer).** `POST /predict` gains an optional `ai` block: model C's "likely" and "possible" 1 h / 2 h
  zones, only on replays for now (`null` otherwise). `Village` and `Alert` gain optional `ai_minutes_left`. New file
  `model/artifacts/replay_ai.parquet` (+ `.json`) written by `model.replay_ai` (`make replay-ai`), new keys
  `paths.replay_ai` and section `ai_layer:`. Additive: C never creates, changes or sends a flag; B stays the model of
  record. Affected: dashboard (#53 draws it).

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

### `model/artifacts/risk_today.parquet` → `api/risk.py` *(added v0.4, #28)*
Written by `python -m model.risk score` (#27). Path: `config.yaml → paths.risk_today`. One row per 375 m cell and day:

| Column | Type | Meaning |
|---|---|---|
| `date` | str `YYYY-MM-DD` (or date/timestamp) | the day the risk is for. The API serves only the **latest** date in the file |
| `lat`, `lon` | float | cell centre (WGS84) |
| `score` | float 0–1 | probability-like risk score |
| `level` | str | `low \| moderate \| high \| very_high`, set by the model (its thresholds) |
| `top_factors` | list[str], or one str separated by `;` | most important factors first, plain words (e.g. `wind`, `dryness`, `past fires`) |

Extra columns are ignored. Rows may cover only part of the country (missing cells are simply not drawn).
A file without one of these columns makes `GET /risk` answer 500 naming the missing columns.

### `data/out/detections.parquet` → `api/detections.py` *(added v0.5, #29)*
One row per satellite detection (VIIRS 375 m): `lat, lon (float), t (UTC timestamp)` required; optional `satellite,
frp (MW), confidence (n|h), daynight`, `country` (rows other than `DZA` are dropped) and `flare` (bool, dropped when true).
FIRMS names `latitude`, `longitude`, `sat`, `conf` are accepted. The API keeps rows north of `scope.lat_min` and removes
gas flares (a 750 m block lit on ≥ `fire_map.flare_min_days` days across ≥ `fire_map.flare_min_years` years).

### `data/out/history_grid.parquet` → `api/detections.py` *(added v0.5, #29)*
One row per grid cell: `lat, lon (cell centre), count (int)` required; optional `years` (years with fire), `last_year`,
`first_year`. Build it from the detections with `python -m api.detections build-history`; without it the API
aggregates `detections.parquet` itself (`fire_map.history_cell_deg`), and without either it serves a stub.

### `model/artifacts/` → API (git-ignored; share via Drive)
| File | Writer | Content |
|---|---|---|
| `model_c_<tag>.txt`, `features_<tag>.json` | `model.train` | LightGBM booster + feature list (`tag` = `mixed` or `dza`) |
| `thresholds.json` | `model.evaluate` | tuned `rate_m_per_min` for A and B, `prob` threshold per C |
| `scoreboard.json` | `model.evaluate` | per holdout × model metrics (shape in §2, `GET /scoreboard`) |
| `api_manifest.json` | `model.export` | what the API loads: rates for A/B and the shipped C (or `null`) |
| `risk_today.parquet` | `model.risk` | today's risk per cell (above, v0.4) |
| `replay_ai.parquet` (+ `.json`) | `model.replay_ai` | model C's zones per holdout pass: `holdout, t, lat, lon, likely_min, possible_min` (v0.6) |

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
It also stores the fire and runs the auto rule, which creates **pending** flags (nothing is sent). "Start a fire here" = this call with one point and no `fire_id`.

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
- `wind` omitted → Open-Meteo 10 m wind at the fire centroid: the vector mean of the hour nearest `time` (UTC) and the next `forecast.mean_hours` (2) hours, the same definition as the training features `wind_speed_2h`/`wind_from_2h` (3 s timeout, cached 15 min): `time` within `now - forecast.past_days` … `now + 7 days` → forecast API (`wind_source: "forecast"`); older → archive API, ERA5 (`"reanalysis"`); any error, timeout or missing value → `config.yaml → weather_default` (`"config_default"`). A request `wind` always wins (`"request"`).
- `wind_source`: `request | forecast | reanalysis | config_default`.
- `ai` *(optional, v0.6, #52)*: model C's advice next to B, or `null` (live fires; no `replay_ai.parquet`; no
  precomputed pass within `ai_layer.match_min` of `time`). It never creates or changes a flag.
  ```json
  "ai": {"model": "C_dza", "label": "AI estimate (model C), check before acting", "time": "2021-08-10T12:49:00Z",
         "likely_recall": 0.9, "possible_recall": 0.99,
         "zones": {"type": "FeatureCollection", "features": [
           {"type": "Feature", "properties": {"horizon_min": 60, "confidence": "likely"}, "geometry": {"...": "..."}}]}}
  ```
  `confidence: likely` = the zone that caught 90 % of burned cells on C's validation fires, `possible` = 99 %
  (Kabylie 2021, 1 h: likely flags 15 % of the cells around the fire and catches 93 % of burns; possible 46 % / 98 %;
  B 64 % / 98 %). `time` is the satellite pass C answered for. C used that pass's real (ERA5) wind, not the request's.
  C only sees cells within 6 km of the fire (data step 7).
- `Village.ai_minutes_left` / `Alert.ai_minutes_left` *(optional, v0.6)*: C's arrival at the `possible` level from
  its cell under the village; `null` = C has no cell there or the fire does not reach it within 2 h. Minutes come in
  C's steps (20, 30, 45, 60, 75, 90, 105, 120), so 20 means "within 20 min".
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

### Operator token (write endpoints)
`POST /alerts`, `POST /alerts/{id}/approve`, `POST /alerts/{id}/reject`, `POST /alerts/{id}/cancel` and `POST /reset`
take a header `X-Operator-Token`, compared with the env var `OPERATOR_TOKEN` (`.env`).
- `OPERATOR_TOKEN` set → a missing or wrong header gets **401**. The demo sets it.
- `OPERATOR_TOKEN` unset or empty → dev mode: allowed, and the API logs one warning.

`POST /predict` and every `GET` stay open.

### Alert object (used by every alert endpoint and both streams)
```json
{
  "id": "al_0001",
  "fire_id": "fire_001",
  "village_id": "osm:123456",
  "village_name": "Village X",
  "level": "leave_now",
  "source": "ai_spread",
  "status": "sent",
  "created_at": "2026-11-20T07:37:33Z",
  "scenario_time": "2021-08-09T12:00:00Z",
  "approved_at": "2026-11-20T07:38:02Z",
  "rejected_at": null,
  "reject_reason": null,
  "cancelled_at": null,
  "edited": false,
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
- `level`: `get_ready | leave_now | update | preventive`.
- `source`: `ai_spread` (the `/predict` rule), `ai_risk` (the daily risk job, preventive flags), `manual` (operator).
- `status`: `pending → sent | rejected`, then `sent → cancelled`. Only `sent` and `cancelled` alerts ever reach the phones.
- Times: `created_at` = flagged (or sent, for manual alerts), `approved_at` = sent, `rejected_at` + `reject_reason`, `cancelled_at`.
  Every action is also written to the API log.
- `edited`: the operator changed the texts when approving.
- `texts` keys: `ary` (Darija), `kab` (Kabyle), `ar`, `fr`, `en`. A language appears only once its checked text exists in `alert/texts.json`.

**Auto rule** (runs on every `/predict`, per fire and village). It only creates or updates **pending** flags:
- A village crossing into level L (`get_ready`/`leave_now`) with no alert at level ≥ L sent and none pending → a pending flag (`source: "ai_spread"`, event `flag`).
- A pending flag whose village changes level or minutes is updated in place: the level only goes up, texts are re-rendered (event `flag_updated`).
- `get_ready` sent and the village escalates to `leave_now` → a new pending `leave_now` flag.
- A village with a sent alert whose computed status falls to `safe` → one pending `update` flag.
- A rejected flag at level L is not re-created for the same fire and village unless the level escalates.
- Cancelling a sent alert does not re-arm the rule at that level.

### `POST /alerts/{id}/approve` *(added v0.2)*
Optional body (edits made by the operator before sending):
```json
{"texts": {"en": "Edited text."}, "radius_km": 8}
```
- `texts`: replaces those languages only (keys from `ary kab ar fr en`, non-empty) and sets `edited: true`.
- `radius_km`: `0 < radius_km ≤ 50`, sets `area.radius_km`.

→ 200 Alert with `status: "sent"`, `approved_at` set. It pushes `alert` to the phones and `alert_sent` to `/events`.
404 unknown id, 409 if the alert is not pending, 422 bad body, 401 bad token.

### `POST /alerts/{id}/reject` *(added v0.2)*
```json
{"reason": "smoke from a controlled burn"}
```
→ 200 Alert with `status: "rejected"`, `rejected_at` and `reject_reason` set. Event `alert_rejected` on `/events`; nothing goes to the phones.
404 unknown id, 409 if not pending, 422 if `reason` is empty.

### `POST /alerts`: manual extra alert
```json
{"village_id": "osm:123456", "fire_id": "fire_001", "level": "leave_now"}
```
→ 200 Alert object, **sent at once** (`source: "manual"`, `status: "sent"`): the operator's click is the approval.
404 if the village is not within 15 km of an active fire.

### `POST /alerts/{id}/cancel`
No body → 200 Alert object with `status: "cancelled"`, `cancelled_at` set. It pushes a `cancel` event to the phones and
`alert_cancelled` to `/events`. It does not re-arm the auto rule at that level for that village.
404 if the id is unknown, 409 if the alert is not `sent` (a pending flag is rejected, not cancelled).

### `GET /alerts/{id}/cap.xml` *(added v0.3, #26)*
No token (public once sent). → 200 `application/xml`: an OASIS **CAP 1.2** message (`urn:oasis:names:tc:emergency:cap:1.2`),
the one the operators' cell broadcast centres would receive. 404 unknown id, 409 if the alert is `pending` or `rejected`
(never published).
- `sent` alert → `msgType` `Alert`, `identifier` `<cap.identifier_prefix>.<alert id>` (e.g. `DZ.WILDFIRE.al_0001`),
  `sent` = `approved_at` (UTC, `YYYY-MM-DDThh:mm:ss+00:00`).
- `cancelled` alert → `msgType` `Cancel`, `identifier` `<…>.<alert id>.cancel`, `sent` = `cancelled_at`,
  `references` = `sender,identifier,sent` of the original Alert message.
- `sender`, `senderName`, `status` (`Exercise` in the demo) come from `config.yaml` `cap:`. `scope` is `Public`.
- One `<info>` per language in `texts`: `language` `ar`/`ary` → `ar-DZ`, `kab` → `kab-DZ`, `fr` → `fr-DZ`, `en` → `en`;
  `category` `Fire`, `event` `Wildfire`, `headline` from `alert/texts.json` (fallback `en`), `description` = the text,
  `parameter`s `minutes_left` (left out when null), `distance_km`, `leave_toward`, `data_age_min`, `wildfire_alert_id`,
  and `<area>` with `areaDesc` = village name and `circle` = `lat,lon radius_km`.

| `level` | `responseType` | `urgency` | `severity` | `certainty` |
| --- | --- | --- | --- | --- |
| `leave_now` | `Evacuate` | `Immediate` | `Extreme` | `Likely` |
| `get_ready` | `Prepare` | `Expected` | `Severe` | `Likely` |
| `preventive` | `Monitor` | `Future` | `Moderate` | `Possible` |
| `update` | `Monitor` | `Expected` | `Moderate` | `Possible` |

Simulated hand-off: when an alert becomes `sent` or `cancelled`, the API logs one line
`CBC hand-off (simulated): <identifier> <msgType> area=<lat,lon r> km` (logger `api.cap`). No new SSE event, no new Alert field.

### `GET /alerts?fire_id=<id>&status=<status>` *(added v0.1, `status` v0.2)*
→ `[Alert, ...]` in creation order. Both filters are optional. `status` is one of `pending | sent | rejected | cancelled`.

### `GET /alerts/stream?village_id=<id>`: push stream for phones (SSE)
`text/event-stream`. Only sent alerts and cancels: a pending or rejected flag never appears here. Events:
```
event: hello
data: {}

event: alert
data: {Alert object, status "sent"}

event: cancel
data: {Alert object, status "cancelled"}

: ping            (every 15 s keep-alive)
```
`village_id` omitted = every alert (demo default, like phones in the whole area). Browsers reconnect automatically.

### `GET /events`: push stream for the dashboard (SSE) *(added v0.2)*
`text/event-stream`. First `event: hello` (`data: {}`), then `: ping` every 15 s. Every other event's `data` is the Alert object:

| Event | When |
|---|---|
| `flag` | a new pending alert (AI flag) |
| `flag_updated` | a pending alert changed (level, minutes, texts) |
| `alert_sent` | approved, or a manual alert sent |
| `alert_rejected` | rejected |
| `alert_cancelled` | a sent alert cancelled |

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
Serves `model/artifacts/scoreboard.json` as is. Before the first evaluation it serves a stub of the same shape
with `"stub": true`, `"status": "not measured yet"`, one entry per `config.yaml → holdouts` and every metric `null`
(`api/scoreboard.py`). The dashboard shows `null` or a missing key as "not measured".
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
  "replay_counter": {"holdout": "kabylie_2021", "village": null, "model": null, "lead_min": null,
                     "old_method": null, "old_method_lead_min": null, "status": "not measured yet"},
  "ship_c": {"rule": "C ships only if it beats B on missed villages and lead time", "decision": "not measured yet"}
}
```
(All values are `null` here on purpose. Real numbers come only from `model.evaluate`.)
- `replay_counter` *(optional, #21)*: the counter on the replay fire, read as "`village` warned `lead_min` before
  the fire arrived (model `model`); `old_method`: `old_method_lead_min`". `old_method` is a short label for the
  comparison (for example how the village is warned today); minutes are integers. If the key is missing or any of
  `village`, `lead_min`, `old_method_lead_min` is `null`, the dashboard shows "not measured".
- Model keys are free-form (`A`, `B`, `C_<tag>`); the dashboard shows whichever are present. Extra keys
  (`n_rows`, `n_burned_cells`) are ignored.
- `ship_c.decision` is always one string (`"ship C_<tag>"`, `"keep B"` or `"not measured yet"`). The reason per C
  model is in the optional `ship_c.decision_by_model` (`{"C_dza": "keep B: kabylie_2021: misses 4 villages, B misses 1"}`).
  `model.evaluate` also writes extra per-holdout sections (`matched_recall`, `villages_where_c_has_cells`,
  `wind_robustness`); the dashboard ignores them.

### `GET /risk` *(added v0.4, #28)*
Today's risk layer, simplified for the map, and the very-high-risk places. No token.
```json
{
  "date": "2026-11-20",
  "stub": false,
  "generated_at": "2026-11-20T05:10:00Z",
  "cell_deg": 0.05,
  "flag_level": "very_high",
  "cells": [{"lat": 36.625, "lon": 4.125, "score": 0.91, "level": "very_high"}],
  "places": [
    {"id": "osm:123456", "name": "Village X", "lat": 36.62, "lon": 4.11, "distance_km": 1.3,
     "score": 0.91, "level": "very_high", "top_factors": ["wind", "dryness", "past fires"],
     "alert_id": "al_0007", "alert_status": "pending"}
  ]
}
```
- `cells`: the file's cells merged onto a `cell_deg` lattice (`config.yaml → risk.display_cell_deg`), keeping the
  **highest** score and its level; `lat`/`lon` is the centre of a `cell_deg` × `cell_deg` square. Only levels at or above
  `risk.min_level_shown` (`moderate`) are sent. Highest score first.
- `places`: places (`places.parquet`, or one stub place per cell) within `risk.place_radius_km` of a cell at
  `flag_level`, highest score first, at least `risk.min_flag_spacing_km` apart, at most `risk.max_flags`.
- **Preventive flags:** each listed place gets one pending Alert (`level: "preventive"`, `source: "ai_risk"`,
  `fire_id: "risk_<date>"`, `minutes_left: null`, `distance_km` = to the very-high cell, empty `fire_direction` and
  `leave_toward`, the `preventive` text) through the normal approval
  queue (event `flag` on `/events`). A place already flagged that day, whatever its status (pending, sent, rejected,
  cancelled), is not flagged again; `alert_id`/`alert_status` point at that alert. Flags are created when `/risk` is
  read (the dashboard reads it on load), so after `POST /reset` they come back on the next read.
- `stub: true` (and `generated_at: null`) = `risk_today.parquet` is missing: deterministic **fake** cells over northern
  Algeria and places named `STUB place …`. Not real data.

### `GET /detections?since=&until=` *(added v0.5, #29)*
Satellite detections for the fire map, newest first. No token. Without `since`: the `fire_map.default_hours` (168 h)
before the newest detection. ISO times; a bad time → 422.
```json
{"stub": false, "newest": "2026-08-30T10:40:00Z", "since": "2026-08-23T10:40:00Z", "until": "2026-08-30T10:40:00Z",
 "count": 365, "truncated": false,
 "detections": [{"lat": 36.745, "lon": 5.988, "t": "2026-08-30T10:40:00Z", "satellite": "SNPP", "frp": 25.2,
                 "confidence": "n", "daynight": "D"}]}
```
At most `fire_map.max_points` rows; `truncated: true` when more matched. The dashboard splits them into the last 24 h
before `newest` and 1–7 days ago.

### `GET /history` *(added v0.5, #29)*
Fire history grid, all years. No token.
```json
{"stub": false, "source": "grid", "cell_deg": 0.05, "first_year": 2012, "last_year": 2026, "max_count": 121,
 "cells": [{"lat": 36.625, "lon": 4.125, "count": 12, "years": 4, "last_year": 2021}]}
```
`source`: `grid` (history_grid.parquet), `detections` (aggregated by the API) or `stub` (fake, with `stub: true`).

### `GET /health` *(added v0.1)*
```json
{"ok": true, "fires": 1, "phones_connected": 4, "dashboards_connected": 1, "pending_alerts": 3,
 "model_c_exported": false, "places": "real", "replay": "real"}
```
`phones_connected` = clients on `/alerts/stream`, `dashboards_connected` = clients on `/events` (v0.2),
`pending_alerts` = alerts waiting for the operator.
`places`/`replay` = `stub` until the data files exist. Check `phones_connected` before each demo run.

### `POST /reset` *(added v0.1, demo only)*
Clears fires and alerts between rehearsals → `{"ok": true}`. Needs `X-Operator-Token` (401 otherwise, when the token is set).
