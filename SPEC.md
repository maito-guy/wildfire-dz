# Wildfire early warning — build spec

**Status:** v0.2, 2026-11-20. Matches Scaffold v0.1.
**Product:** see the PRD. **Frozen API and data shapes:** [`docs/contracts.md`](docs/contracts.md) (it wins on any field name).
**Time box:** 24 h from kickoff (H0) to the demo (H24).

This file says **what we build, with which stack, who owns which folder, and when each piece is done**. The work itself is tracked as GitHub issues labelled `phase 1|2|3` and `frontend|backend`.

---

## 1. What we build

1. **Spread prediction:** 1 h and 2 h danger zones around a fire, tuned so at least 95% of cells that really burned fall inside them.
2. **Minutes left per village:** for every place within 15 km. Status is `safe` (more than 120 min or no zone nearby), `get_ready` (60–120 min) or `leave_now` (under 60 min).
3. **Emergency alert on phones:** a React Native app on Android test phones stands in for cell broadcast. It shows a loud, full-screen alert in Darija, Kabyle, Arabic and French.
4. **Civil Protection dashboard:** a map with zones, villages sorted by minutes left, Send and Cancel buttons, replay of a held-out fire, and "Start a fire here".
5. **Scoreboard:** models A, B and C on the held-out fires, with missed villages, lead time and false alarms.

Out of scope: real cell broadcast, iOS phones as alert receivers, road routing, accounts, the Sahara, Telegram, sirens.

---

## 2. Stack and why

| Part | Folder | Stack | Why |
| --- | --- | --- | --- |
| API | `api/`, `core/` | Python 3.11, FastAPI, Pydantic v2, numpy, shapely | Same language as the model, which the API imports directly: no second service and no network hop. Already scaffolded and tested |
| Storage | `data/out/*.parquet`, in memory | Parquet files plus in-memory state | One demo laptop, read-mostly data, ≤ 10,258 places. A database adds setup and nothing for the demo. Parquet is what the ML pipeline already writes |
| Model | `model/` | LightGBM, scikit-learn, pandas | Trains in minutes on a laptop and shows which features matter. Baselines A (buffer) and B (wind/slope ellipse) need no training |
| Data pipeline | `data/firedata/` | 5 Python scripts (FIRMS, Open-Meteo ERA5, Copernicus DEM, ESA WorldCover) | Already written. Run on a laptop, because the data sources block cloud machines |
| **Mobile alert app** | `mobile/` *(new)* | **Expo (React Native) + TypeScript**, `react-native-sse`, `expo-audio`, `expo-keep-awake`, `expo-location`, `expo-router` | Only a native app can play the alarm when the phone is on silent and keep the screen on. The current web page `/alert/` can't keep the screen on over plain HTTP. Expo reloads the app on a real phone in seconds |
| Dashboard | `dashboard/` | Vanilla JS + Leaflet (bundled in the repo), no build step | Already works: replay, start a fire, village list, Send/Cancel, alert log, reset. Nothing to install, and it loads fast over slow 3G |
| Phone web fallback | `alert/` | Static HTML + SSE | Kept as a backup receiver for any phone without the app, iPhones included |
| Tooling | — | `uv` or pip + venv, `ruff`, `pytest`, GitHub Actions; npm, `tsc`, ESLint for `mobile/` | CI must stay green on every PR |

### 2.1 SSE or WebSocket? We keep **SSE**.
Alerts only travel one way, from the server to the phones. Server-sent events (SSE) fit that exactly:
- **Plain HTTP** (`GET /alerts/stream`). It passes proxies and phone hotspots, and is one FastAPI `StreamingResponse`. It is already built and tested.
- **Reconnects on its own** and has a 15 s keep-alive ping.
- Phones never need to send anything (by design: they report no location).

A WebSocket only pays off when the client also has to talk back fast (chat, games). Here we'd add complexity for nothing. React Native has no built-in `EventSource`, so the app uses the small `react-native-sse` library.

### 2.2 How the phone decides an alert is for it
Each alert carries `area: {lat, lon, radius_km}`. The app has two modes:
- **Pinned village** (the demo default): the app subscribes to `/alerts/stream?village_id=<id>`.
- **GPS:** the app subscribes to every alert and checks locally whether the phone is inside `area`. **The server never learns where the phone is**, as Algeria's data-protection law (18-07) requires, and the same way real cell broadcast works.

---

## 3. Who works where

| Person | Folder | Branch | Hands over through |
| --- | --- | --- | --- |
| **Full stack (lead)** | `api/`, `core/` (with AI), `mobile/`, `dashboard/` | `fullstack`, or one branch per issue | API contract, `docs/contracts.md` |
| **AI** | `model/` | `ai` | Files in `model/artifacts/` (see §4) |
| **Electronics / data** | `data/` | `data` | `data/out/*.parquet` on the shared Drive |
| **UI/UX 1** | Designs for `mobile/` (alert screen), checking the holdout fires | `uiux-alert` | Figma, then review of the screen PRs |
| **UI/UX 2** | Designs for `dashboard/`, slides | `uiux-dashboard` | Figma, then CSS PRs |
| **Commerce** | `alert/texts.json` (translations), `pitch/` | `commerce` | Checked texts in the JSON |

---

## 4. How the AI work plugs in

The AI teammate never edits `api/`. They own `model/`, and the API only reads files they publish:

```
data/out/train.parquet ──► model.train ──► model_c_<tag>.txt + features_<tag>.json
                                   │
                         model.evaluate ──► thresholds.json + scoreboard.json
                                   │
                    model.export --tag mixed ──► api_manifest.json   (the "ship it" switch)
                                   │
        api/predictor.py reads the manifest at startup ──► POST /predict uses C, falls back to B
```

Rules:
1. **The loop:** `make model` (train mixed + Algeria-only, then evaluate), then `make export TAG=mixed`, but only if C beats B on missed villages and lead time (PRD rule). Otherwise `make export` with no tag ships tuned A/B only.
2. **Artifacts are not in git** (`model/artifacts/*` is ignored). Share them through the Drive folder; the demo laptop copies them into `model/artifacts/`.
3. **The one integration seam:** model C needs per-cell features at prediction time (terrain, fuel, weather) that are identical to the training features. That means one shared function, `core/features.py: build_cell_features(lat, lon, burning, time, wind) -> DataFrame`. `data/05_build_table.py` (training) and `api/predictor.py` (serving) both call it, so training and serving can't drift apart. Terrain and fuel are precomputed once as a 375 m raster of northern Algeria, so the API never downloads anything live.
4. **Fail-safe:** if C raises an error, times out (`api.predict_timeout_s`) or has no features, the API answers with B and sets `fallback_reason`. It never returns nothing.
5. **Contract changes** (`docs/contracts.md`, `api/schemas.py`) go in one PR with a note in the team chat.

---

## 5. User flows

### 5.1 Demo (≤ 3 min, see `docs/demo-script.md`)
1. The operator opens `/dashboard/` and picks the Kabylie 2021 replay, then presses Play. At each pass the 1 h and 2 h zones appear next to what really burned.
2. The village list re-sorts by minutes left; red rows say **LEAVE NOW** in words.
3. A judge clicks "Start a fire here". Zones appear in under 10 s, and villages within 15 km get minutes left.
4. Villages that cross a threshold get an automatic alert. The test phones pinned to those villages sound a full-screen alert within 30 s of the click.
5. The operator presses **Cancel** on one alert. That phone shows "Alert cancelled by Civil Protection".
6. Show the scoreboard: A vs B vs C, Algeria-only vs mixed, false alarms reported honestly.

### 5.2 Resident (phone)
1. The app is open and armed: green "Connected", pinned to a village or using GPS.
2. A `get_ready` alert arrives. The phone plays a looping alarm at full volume even on silent, vibrates, and keeps the screen awake. It shows **GET READY**, the village, minutes left, the fire's distance and direction, the direction to leave with an arrow, "satellite pass N min ago", and the text in the chosen language.
3. A `leave_now` alert replaces it, red, with **LEAVE NOW**.
4. An `update` alert shows "the fire is no longer moving toward you". A `cancel` event shows "cancelled". The app never says "safe" on its own.
5. **Connection lost:** a red banner reading "Not connected to the alert server — reconnecting", with automatic retry.

### 5.3 Operator (dashboard)
1. Sees active fires, the 1 h and 2 h zones, the data age, the model in use (and the fallback reason), and a stale-data banner after 3 h.
2. Sends an extra alert to a village the model hasn't flagged, or cancels a wrong one in one tap.
3. Sees how many phones are connected (`/health → phones_connected`).

---

## 6. Phases (24 h)

| Phase | Hours | Done when |
| --- | --- | --- |
| **Phase 1: foundations** | H0–H8 | Repo at root with CI green; real `places.parquet` and `replay_passes.parquet` loaded; Kabylie 2021 replays on the dashboard with model B; the React Native app receives a test alert over SSE on one Android phone; the AI has the training table and baselines tuned |
| **Phase 2: end to end** | H8–H14 | Click → zones → villages → **3 Android phones on silent sound** within 30 s, 5 runs out of 5; the alert screen is finished in 4 languages; wind comes from the Open-Meteo forecast |
| **Phase 3: real model and demo** | H14–H24 | Model C trained, evaluated and (if it wins) served through the shared feature builder; scoreboard on the dashboard; full acceptance check passed on the demo rig; code freeze at H21; backup video recorded |

Sleep in two shifts. Full stack and AI never sleep at the same time.

---

## 7. Definition of done (every issue)
- The issue's acceptance criteria are all checked and shown in the PR (screenshot, command output, or timing).
- `ruff check .` and `pytest -q` pass in CI. For `mobile/`: `npx tsc --noEmit` and `npx eslint .`
- No new hard-coded thresholds: they go in `config.yaml`.
- `docs/contracts.md` and `api/schemas.py` are updated together if a shape changed.
- Anything touching phones has been tested on a **real Android phone**, not only the emulator.

## 8. Acceptance check on the demo rig (Phase 3)
1. The Kabylie 2021 replay steps through every pass with zones and the "really burned next" layer.
2. Click → phone sounds in under 30 s, 5 runs out of 5 (times recorded).
3. 3 phones on silent all sound; a native speaker checks each of the 4 languages on screen.
4. Cancel reaches the phone.
5. Model C is forced to fail → the dashboard shows "B (fallback)".
6. No internet → the demo still runs on the hotspot (wind falls back to the config value, and the map tiles are cached or the background is blank).
7. `/health` shows `phones_connected` = the number of phones before each run.

## 9. Open questions
| Question | Default until answered |
| --- | --- |
| Civil Protection number in the "Leave now" text | `[number, to confirm]` stays in `texts.json` |
| Is the export's licence OK for a public repo? | Commerce checks before the pitch; the repo is already public |
| Darija in Arabic script or Latin? Kabyle in Latin or Tifinagh? | Darija in Arabic script (right-to-left), Kabyle in Latin script |
| Where on Drive the data and model files live | Folder link pinned in the team chat and the README |
