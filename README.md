# Wildfire early warning: northern Algeria (HackAlgeria / Makers² 2026)

We predict where a fire will be in 1 h and 2 h, tell each village how many minutes it has left,
and send an emergency alert to every phone in the area (UK-style, simulated on test phones).

**Build spec (stack, owners, phases):** [`SPEC.md`](SPEC.md). **Contracts:** [`docs/contracts.md`](docs/contracts.md). **Work:** GitHub issues, labelled `phase 1|2|3` and `frontend|backend`.

## 5-minute setup

Needs Python **3.11**, Node **22.12+** and git. On Windows use WSL, or run the commands inside the Makefile by hand.
No `python3.11` on your machine? `uv venv -p 3.11 .venv && uv pip install -p .venv -r requirements-dev.txt` does the same as `make setup`.

```bash
git clone <repo-url> && cd <repo>
make setup            # .venv + deps + .env from .env.example (or the uv command above)
npm ci                # root install: npm workspaces (dashboard, api) + Turborepo
npx turbo dev         # API on http://localhost:8000 + dashboard on http://localhost:5173/dashboard/ (or `make dev`)
```

`.venv` must exist before any turbo command: the `api` workspace (`api/package.json`) only wraps the Python tools
(`.venv/bin/python -m uvicorn`, `.venv/bin/ruff`, `.venv/bin/python -m pytest`) and runs them from the repo root.

- **Every check:** `npx turbo lint typecheck test build` (ruff + pytest for the API; ESLint, `tsc` and `vite build` for the
  dashboard). Turborepo caches each task, so a second run only re-runs what changed. The Python checks also run alone
  with `make lint test`.
- **Dashboard (Civil Protection):** in dev, `http://localhost:5173/dashboard/` (Vite hot reload, API calls proxied to :8000).
  For the demo, `make dashboard-build` writes `dashboard/dist/` and `make api` serves it at `http://localhost:8000/dashboard/`.
  Without a build, the API still starts and logs a warning.
- **One side only:** `make api` (API alone, also serves the built dashboard) or `make dashboard-dev` (Vite alone).
- **One lockfile:** the root `package-lock.json`. Add dashboard packages with `npm install <pkg> --workspace dashboard`.
- After changing `api/schemas.py`, run `npm run gen:api --workspace dashboard` (API running) and commit `dashboard/src/api/schema.ts`.
- Test phone alert page: `make lan-ip` prints `http://<laptop-ip>:8000/alert/`. Open it on each phone (same Wi-Fi) and tap **arm**.
- API docs (auto): `http://localhost:8000/docs`

Without data files, the API runs on **stubs**: fake villages (`stub:` ids) and one synthetic fire, all flagged `stub`.
Frontend work can start right away. Real data drops in with no code change (see `data/README.md`).

## Run with Docker

Needs only Docker with Compose v2 (no Python or Node on the machine). One image holds the API, the built dashboard and
the phone page; `docker-compose.yml` runs it as one `api` service on port 8000 (`PORT=8040 make docker-up` to change it).

```bash
make docker-up        # docker compose up -d --build → http://localhost:8000/dashboard/ and /alert/
make docker-logs      # follow the API logs
make docker-down      # stop and remove the container
```

- `.env` is read at runtime (`env_file`, optional), never copied into the image.
- `data/out/` and `model/artifacts/` are mounted **read-only** from the repo folder. Without them the API runs on stubs,
  as in the 5-minute setup. After dropping new files in, `docker compose restart` picks them up: no rebuild.
- Rebuild (`make docker-up`) only after a code change. `GET /health` shows `places: real` once `data/out/places.parquet` is there.
- The container runs as a non-root user (uid 10001) and has a health check on `/health` (`docker compose ps`).

### Demo day (Docker)

1. `cp .env.example .env`, then set `OPERATOR_TOKEN` in `.env` (write endpoints need it; enter the same token in the
   dashboard's Settings panel).
2. Put the data files in `data/out/` (`*.parquet`) and the exported model in `model/artifacts/`.
3. `make docker-up`, then `docker compose ps` until the service is `healthy`.
4. Projector/operator: open `http://<laptop-ip>:8000/dashboard/` (`make lan-ip` prints the laptop address).
5. Phones (same Wi-Fi): open `http://<laptop-ip>:8000/alert/` and tap **arm**.
6. New data or model files during the day: drop them in, then `docker compose restart` (no rebuild).

## Layout

| Folder | What | Owner |
|---|---|---|
| `data/` | firedata pipeline (5 scripts, kept as is) → `data/out/*.parquet` | Electronics (+ AI) |
| `model/` | baselines A/B, LightGBM C, threshold tuning, scoreboard, export | AI |
| `api/` | FastAPI: contract endpoints, replay, impact (minutes left), alert rules + SSE stream | Full stack |
| `dashboard/` | Civil Protection dashboard: fire map, risk layer, AI approval queue, alerts, scoreboard, planting (React + TypeScript + Vite, react-leaflet; built into `dashboard/dist/` and served by FastAPI) | Full stack (design: UI/UX 2) |
| `alert/` | phone web page that imitates a cell-broadcast alert (demo) + `texts.json` (4 languages) | Full stack (texts: Commerce) |
| `core/` | config loader + geometry shared by model and api | AI |
| `docs/` | contracts, demo script | all |
| `pitch/` | deck, Q&A sheet, facts | Commerce + UI/UX 2 |

Every threshold and path lives in **`config.yaml`**, never in code.

## Model loop (AI)

```bash
make check-columns    # does train.parquet match config.yaml → columns?
make model            # train C (mixed + Algeria-only), tune thresholds, scoreboard on held-out fires
make export TAG=mixed # publish for the API, only if C beats B on missed villages and lead time
```

Rules: evaluate on **whole held-out fires** (Kabylie 5–16 Aug 2021, Jijel/Guelma 26 Aug–8 Sep 2026), always next to A and B.
Thresholds target ≥ 95% of burned cells inside the zone, and false alarms are reported honestly. Training weather is ERA5
reanalysis (a perfect forecast); say so wherever accuracy is quoted. No number gets invented: if it's not measured, it's `null`.

## Git workflow

- `main`: PRs only, CI (ruff + pytest) must pass, 1 review. (Not enforced by GitHub yet: a repo admin should turn on branch protection.)
- One branch per role: `ai`, `fullstack`, `uiux-alert`, `uiux-dashboard`, `data`, `commerce`. Keep PRs small and frequent.
- Never commit data, `.parquet`, model artifacts or `.env`. `FIRMS_MAP_KEY` lives in `.env` only.
- Changing `docs/contracts.md` or `api/schemas.py` needs a note in the team chat naming who it affects.

## Demo-day notes

- Map tiles come from OpenStreetMap, so they need internet. Keep a phone hotspot as backup.
- Phones over plain HTTP can't use Wake Lock, so set each test phone's auto-lock to "never".
- `POST /reset` (dashboard → **Reset demo**) between rehearsals. `GET /health` shows `phones_connected`.

Credit: fire detections from NASA FIRMS (VIIRS 375 m) via the Algeria Fire Map open-source export; OpenStreetMap; Copernicus DEM; ESA WorldCover; Open-Meteo (ERA5).
