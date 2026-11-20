# Wildfire early warning: northern Algeria (HackAlgeria / Makers² 2026)

We predict where a fire will be in 1 h and 2 h, tell each village how many minutes it has left,
and send an emergency alert to every phone in the area (UK-style, simulated on test phones).

**Build spec (stack, owners, phases):** [`SPEC.md`](SPEC.md). **Contracts:** [`docs/contracts.md`](docs/contracts.md). **Work:** GitHub issues, labelled `phase 1|2|3` and `frontend|backend`.

## 5-minute setup

Needs Python **3.11** and git. On Windows use WSL, or run the commands inside the Makefile by hand.
No `python3.11` on your machine? `uv venv -p 3.11 .venv && uv pip install -p .venv -r requirements-dev.txt` does the same as `make setup`.

```bash
git clone <repo-url> && cd <repo>
make setup            # .venv + deps + .env from .env.example
make test             # all smoke tests should pass
make api              # http://localhost:8000  → dashboard
```

- Dashboard (Civil Protection): `http://localhost:8000/dashboard/`
- Test phone alert page: `make lan-ip` prints `http://<laptop-ip>:8000/alert/`. Open it on each phone (same Wi-Fi) and tap **arm**.
- API docs (auto): `http://localhost:8000/docs`

Without data files, the API runs on **stubs**: fake villages (`stub:` ids) and one synthetic fire, all flagged `stub`.
Frontend work can start right away. Real data drops in with no code change (see `data/README.md`).

## Layout

| Folder | What | Owner |
|---|---|---|
| `data/` | firedata pipeline (5 scripts, kept as is) → `data/out/*.parquet` | Electronics (+ AI) |
| `model/` | baselines A/B, LightGBM C, threshold tuning, scoreboard, export | AI |
| `api/` | FastAPI: contract endpoints, replay, impact (minutes left), alert rules + SSE stream | Full stack |
| `dashboard/` | Civil Protection map, vanilla JS + Leaflet (vendored, no build step) | Full stack (design: UI/UX 2) |
| `mobile/` | **Expo React Native alert app** for Android test phones (loud on silent, keep-awake) | Full stack (design: UI/UX 1) |
| `alert/` | web fallback phone page + `texts.json` (4 languages, read by the app too) | Full stack (texts: Commerce) |
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
