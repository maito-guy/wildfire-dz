# Wildfire early warning: build spec

**Status:** v0.3.1 (2026-11-20): dashboard in React + TypeScript, served by FastAPI. Pivot from v0.2: no mobile app. A Civil Protection dashboard with AI suggestions and alerts approved by an operator, cell broadcast (simulated), and a fire-risk map; a planting module is planned for phase 3.
**Product:** see the PRD. **Frozen API and data shapes:** [`docs/contracts.md`](docs/contracts.md).
**Time box:** 24 h from kickoff (H0) to the demo (H24). Work is tracked as GitHub issues labelled `phase 1|2|3` and `frontend|backend`.

---

## 1. What we build

One **web dashboard** for the Civil Protection operator, plus a **phone web page** that imitates a cell-broadcast alert for the demo.

1. **Fire map** (like Algeria Fire Map): current satellite detections, fire history, and active fires with their predicted 1 h and 2 h zones.
2. **The AI flags places in two ways:**
   - **Spread (now):** for an active fire, which villages it can reach and in how many minutes (`get_ready` 60–120 min, `leave_now` under 60).
   - **Risk (today):** a daily fire-risk map. The places where a fire is most likely to start or spread today are flagged for a **preventive** alert.
3. **Approval queue:** every AI flag becomes a **pending alert**. The operator checks it, can edit the text and the area, then **approves and sends** it or **rejects** it. The operator can also write an alert from scratch. **Nothing reaches the public without a human click.**
4. **Cell broadcast (simulated):** sending an alert builds a standard **CAP 1.2** message (area, level, texts in Darija, Kabyle, Arabic and French). In production it would go to the operators' cell broadcast centres (Mobilis, Djezzy, Ooredoo). In the demo it is shown on screen, and test phones running the `/alert/` web page receive it over SSE and sound.
5. **Scoreboard:** models A, B and C on the held-out fires, with missed villages, lead time and false alarms.
6. **Planting suggestions (phase 3, demo page):** combine fire history, plantable land from Google Earth Engine, and the 2002 planting dataset to suggest **where and what to plant** after a fire, for 2–3 wilayas.

Out of scope: a resident app, real cell broadcast, road routing, accounts beyond one operator token, the Sahara, Telegram, sirens.

---

## 2. How alerts reach people

| | **Cell broadcast** (production) | **SSE** (our system and the demo) |
| --- | --- | --- |
| What it is | Operator cell towers send one message to every phone connected to them in an area | One long-lived HTTP connection from a browser to our server; the server pushes events down it |
| Who receives it | Every phone in the area. No app, no number, no internet; works when the network is jammed | Our dashboard, and the demo phones that open `/alert/` |
| Who triggers it | Only an authority (Civil Protection), through the operators, with a CAP message | Our API, the moment something happens |
| What we build | The approve-and-send flow and the CAP message. The handoff to the operators is **simulated** | `GET /events` (dashboard: new flags, alert status) and `GET /alerts/stream` (phones: sent alerts) |

**Why SSE and not a WebSocket?** Messages only flow one way, from the server to the browser. SSE is plain HTTP, reconnects by itself, works through hotspots and proxies, and is already built. The dashboard's actions (approve, reject, send) are ordinary POST requests.

---

## 3. Stack and why

| Part | Folder | Stack | Why |
| --- | --- | --- | --- |
| API | `api/`, `core/` | Python 3.11, **FastAPI**, Pydantic v2, numpy, shapely | Integrates the AI: it imports the `model/` package and its artifacts in-process (no separate model service). Pydantic models generate the OpenAPI contract the React app types itself from. Already scaffolded and tested |
| Storage | `data/out/*.parquet`, in memory | Parquet plus in-memory state | One demo laptop, read-mostly data; it is what the pipeline writes |
| Spread and risk models | `model/` | LightGBM, scikit-learn, pandas | Trains in minutes on a laptop and explains its features. Baselines A and B need no training |
| Data pipeline | `data/` | FIRMS, Open-Meteo ERA5, Copernicus DEM, ESA WorldCover; **Google Earth Engine** export for the planting layer | Pipeline already written. GEE layers are exported once as GeoTIFF or CSV, so the API never calls GEE live |
| Dashboard | `dashboard/` | **React + TypeScript + Vite**, `react-leaflet` (canvas renderer for thousands of detections), `@tanstack/react-query` for REST, native `EventSource` for SSE, types generated from FastAPI's `/openapi.json` with `openapi-typescript` | Typed components for a dashboard that is growing (map layers, approval queue, risk, scoreboard, planting). Types generated from the API mean the frontend breaks at build time, not at the demo, when a contract changes. Leaflet keeps the scaffold's map logic |
| Demo phone page | `alert/` | Static HTML + SSE + Web Audio | Imitates the cell-broadcast screen with no app. Already built |
| Tooling | root `package.json`, `turbo.json` | venv or uv, `ruff`, `pytest`; npm workspaces (`dashboard`, `api`) with one root lockfile, **Turborepo** (`turbo dev` runs both, `turbo lint typecheck test build` caches every check), `tsc --noEmit`, ESLint, `vite build`; GitHub Actions | One command to run and check both stacks. CI must be green on every PR (Python job + dashboard job) |

---

### 3.1 How the dashboard and FastAPI fit together
- **Dev:** `npx turbo dev` at the repo root starts FastAPI (:8000, reload) and Vite (:5173) together; Vite proxies the API paths and the SSE streams to :8000. Hot reload, no CORS.
- **Demo:** `npm run build` writes `dashboard/dist/`, and FastAPI serves it at `/dashboard/`. One process and one URL on the demo laptop, so phones and the projector only need the laptop's IP.
- **Types:** `npm run gen:api` runs `openapi-typescript http://localhost:8000/openapi.json -o src/api/schema.ts`. Commit the generated file, and regenerate it whenever `api/schemas.py` changes.
- **The phone page** `alert/` stays plain HTML and JS (one small page, no build).

## 4. Who works where

| Person | Folder | Hands over through |
| --- | --- | --- |
| **Full stack (lead)** | `api/`, `core/`, `dashboard/`, `alert/` | The API contract in `docs/contracts.md` |
| **AI** | `model/` (spread and risk; planting rules in phase 3) | Files in `model/artifacts/` (§5) |
| **Electronics / data** | `data/` (FIRMS, weather, terrain, GEE exports) | `data/out/*` on the shared Drive |
| **UI/UX 1 / 2** | Designs for the dashboard, approval queue and phone page; checking the holdout fires | Figma, then CSS PRs |
| **Commerce** | `alert/texts.json` (translations), `pitch/`, the CAP and cell-broadcast story | Checked texts in the JSON |

---

## 5. How the AI work plugs in

The AI teammate works in `model/` and never edits `api/`. The API reads only the files the AI publishes in `model/artifacts/` (shared on Drive, not in git):

| Model | Trained by | Published files | Used by |
| --- | --- | --- | --- |
| **Spread** (A buffer, B physics-lite, C LightGBM) | `make model`, then `make export TAG=mixed` | `api_manifest.json`, `model_c.txt`, `thresholds.json`, `scoreboard.json` | `POST /predict`, which falls back C → B and never returns nothing |
| **Risk** (LightGBM on past fire starts vs non-fire days, per 375 m cell and day) | `python -m model.risk train/score` | `risk_today.parquet` (cell, score 0–1, level, top factors) | `GET /risk`, risk layer, preventive flags |
| **Planting** (phase 3: rules or a small model) | `python -m model.planting` | `planting.parquet` (cell, plantable, suggested species, reason) | `GET /planting` |

The **shared feature builder** `core/features.py` is used by both training and the API, so the features never differ between the two.

---

## 6. User flows

### 6.1 Operator: spread alert (main demo)
1. Opens `/dashboard/`. Sees the fire map with current detections, active fires, and today's risk layer.
2. A fire is active (Kabylie 2021 replay, or a judge clicks "Start a fire here"). The 1 h and 2 h zones appear in under 10 s.
3. The AI flags the villages in the fire's path. They appear in the **Approval queue**, sorted by minutes left: village, minutes, level, distance, direction to leave, and a preview of the text in 4 languages.
4. The operator presses **Approve & send** (optionally editing the text or the radius), or **Reject** with a reason.
5. The system builds the CAP message and simulates the broadcast. The test phones on `/alert/` sound within 30 s of the click, full screen, in 4 languages.
6. Every action (flagged, approved, rejected, sent, cancelled) is logged with the time and who did it. A wrong alert can be **cancelled** in one tap, which sends a cancel message.

### 6.2 Operator: preventive risk alert
1. In the morning, the risk layer shows today's high-risk zones, plus a list of places in "very high" risk with their top factors (wind, dryness, past fires).
2. Places above the risk threshold appear in the queue as **preventive** flags. The operator approves a preventive message ("High fire risk today: no burning, report smoke to 1021") or rejects it.

### 6.3 Resident (demo phone page imitating cell broadcast)
1. Does nothing in advance. In the demo, the phone has `/alert/` open and armed.
2. When an approved alert reaches the area: a loud alarm, full screen, the level, the village, minutes left, the direction to leave, the data age, and the texts in 4 languages (Arabic and Darija right to left).
3. Update and cancel messages replace the screen. The page never says "safe" by itself.

### 6.4 Planting suggestions (phase 3)
1. The operator or a forest-service user opens the **Planting** tab and clicks a burned area or a commune.
2. Sees whether it is plantable, the suggested species, and why (fire history, land type, what was planted in 2002 and how it burned since).

---

## 7. Phases (24 h)

| Phase | Hours | Done when |
| --- | --- | --- |
| **Phase 1: foundations** | H0–H8 | Repo at root with CI green; real places and replay data; the Kabylie 2021 replay runs with model B; AI flags go into a pending queue in the API; the training table is ready and baselines are tuned |
| **Phase 2: end to end** | H8–H14 | Fire map layers; approval queue UI; CAP message; the phone page in 4 languages; a click, then approve, makes **3 phones sound in under 30 s**, 5 runs out of 5; live wind |
| **Phase 3: models and extras** | H14–H24 | Model C served; risk map and preventive flags; scoreboard; planting demo page (if time allows); acceptance check passed; freeze at H21 |

---

## 8. Definition of done (every issue)
- Every acceptance criterion is checked and shown in the PR (screenshot, command output or timing).
- `ruff check .` and `pytest -q` are green in CI; for `dashboard/`: `npm run typecheck`, `npm run lint`, `npm run build`.
- No hard-coded thresholds: they go in `config.yaml`.
- If a shape changed, `docs/contracts.md` and `api/schemas.py` are updated together, with a note in the team chat.
- Anything touching the phone page has been tested on a real phone.

## 9. Acceptance check on the demo rig
1. The Kabylie 2021 replay runs through every pass with zones and the "really burned next" layer.
2. An AI flag appears in the queue → approve → phones sound in under 30 s, 5 runs out of 5.
3. Nothing is sent without approval: a test shows a flag stays pending until the operator approves it.
4. Reject and cancel work and are logged. The CAP message validates against the CAP 1.2 schema.
5. The risk layer renders for today, and high-risk places can be sent as preventive alerts.
6. Model C failing → the dashboard shows "B (fallback)".
7. No internet → the demo runs on the hotspot with the fallback wind.

## 10. Open questions
| Question | Default until answered |
| --- | --- |
| Civil Protection number in the alert texts | `[number, to confirm]` |
| Export licence OK for a public repo? | Commerce checks before the pitch |
| Darija and Kabyle script | Darija in Arabic script (right to left), Kabyle in Latin script |
| Which Earth Engine layers count as "plantable" (slope, soil, land cover, protected areas)? | Owner: AI + Electronics, decided in the planting data issue |
| Format and coverage of the 2002 planting dataset | Electronics inspects it at the start of phase 3 |
