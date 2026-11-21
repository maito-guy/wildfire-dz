# PROGRESS.md: Project memory store

This file is the single source of truth for the project's working state between
sessions: a current snapshot plus the decisions behind it. GitHub holds the
history. The rules for maintaining it are in `RULES.md` section 14. Keep
entries short and factual. Use absolute dates (YYYY-MM-DD).

**Last updated:** 2026-11-21

---

## 1. Current state

- **Phase:** delivery (`RULES.md`, `PROJECT_MANAGEMENT_RULES.md` §9–13). Spec: `SPEC.md` v0.3.1.
- **Running:** wave 5 (2026-11-21): #58 merged (PR #66, closed; real Kabylie replay with `replay_ai.parquet` still to check on the laptop). #59 (approval queue groups) in progress. #20 PR #67 (model C in `/predict`, coded against a test booster; real artifacts on the Drive). #59 waits on #58.
- **Merged 2026-11-21:** #63 (place names, #62), #64 (live FIRMS every 30 min, #61), #65 (FWI cap on the risk layer, closed #57), #60 (shared feature builder `core/features.py`, closed #18; Q-05 answered yes, steps 5/7 take `--terrain raster`). #17 stays open until `static_375m.npz` is on the Drive.
- **Real data:** `make import-export` turns the Algeria Fire Map export (`data/algeria-fire-map-data/`, git-ignored) into detections, history, places, replay passes and the risk layer (D-15). `/detections /history /risk /replay` and `/health` answer `stub: false`/`real` on this machine.
- **Next up:** rebuild `train.parquet` with `--terrain raster` and retrain C (data teammate, local data); #27, #19. #7 blocked only by #5 (bbox confirmation). #30 needs the GEE export and the 2002 dataset. #11 needs humans.
- **Blockers:** #5 bboxes TO CONFIRM; `model/artifacts/` (model C) lives on the Drive, not on this machine; run `make export` on the demo laptop (else B uses the 10 m/min placeholder); #8 #11 need humans (design, translations).

---

## 2. Conventions

| ID | Convention | Source |
| --- | --- | --- |
| C-01 | Integration branch is **`dev`**. Every issue branch starts from `origin/dev`, and every PR targets `dev`. `main` is updated from `dev` only by the owner | D-01 |
| C-02 | Branch names `<type>/<issue>-<slug>`, types `feat fix refactor docs test chore ci`. Conventional Commits with scopes `api`, `model`, `data`, `dashboard`, `alert`, `core`, `ci`, `docs` | kit §9 |
| C-03 | Labels: exactly one of `phase 1`, `phase 2`, `phase 3`, plus `frontend` or `backend`. No type, priority or status labels | D-05 |
| C-04 | Issue body sections: Owner · Why · User flow · What to build (In/Out) · Where · Done when · How to test · Depends on. Dependencies are real GitHub blocked-by links (REST API, because gh 2.45 has no `--blocked-by`) | D-05 |
| C-05 | Python 3.11. Setup: `uv venv -p 3.11 .venv && uv pip install -p .venv -r requirements-dev.txt` (or `make setup`). Checks: `.venv/bin/ruff check .` and `.venv/bin/python -m pytest -q`. In a worktree, use the main checkout's venv: `/home/malikou/Algeria2.0/wildfire-dz/.venv/bin/...` | scaffold |
| C-06 | Dashboard: React + TypeScript + Vite in `dashboard/`. Checks: `npm ci`, `npm run typecheck`, `npm run lint`, `npm run build`. FastAPI serves `dashboard/dist/` at `/dashboard/` only once built (nothing is mounted otherwise; tests expect 404 then). Regenerate `src/api/schema.ts` with `npm run gen:api` (API running) whenever `api/schemas.py` or the endpoints change, and commit it. TypeScript is pinned to ~5.9 (typescript-eslint and openapi-typescript don't support TypeScript 7). Node ≥ 22.12 | SPEC §3.1, #38 |
| C-07 | Every threshold and path goes in `config.yaml`, never in code. `docs/contracts.md` and `api/schemas.py` change together, with a team-chat note | scaffold README |
| C-08 | SSE, not WebSocket: `/alerts/stream` (phones: sent alerts only) and `/events` (dashboard). Write endpoints take an `X-Operator-Token` header | SPEC §2, wave 1 seams |
| C-09 | CI workflow name is `ci`. Merge with `scripts/merge-pr.sh -w ci <pr>...` | kit |
| C-10 | Tests never call the real network; mock HTTP with `httpx.MockTransport` or monkeypatch. `api/tests/conftest.py` makes every Open-Meteo call fail offline; to test a real lookup, pass `client=` to `weather.get_wind` | RULES §7.2, #35 |
| C-11 | Alert lifecycle `pending → sent \| rejected`, then `sent → cancelled`. Only `sent` alerts and cancels reach `/alerts/stream` (public). The dashboard follows `/events` | #36 |
| C-12 | `AlertStore.flag(fire_id, v, level, source, scenario_time, data_age_min)` is the single entry point for AI flags. Risk flags (#28) use `source="ai_risk"`, `level="preventive"` | #36 |
| C-14 | Dashboard write calls send `X-Operator-Token` from `localStorage["operatorToken"]` (Settings panel) | #38 |
| C-15 | CAP settings live in `config.yaml → cap`. The demo uses status `Exercise`; `Actual` only for a real deployment. CAP is built with the stdlib; `lxml` is test-only (XSD in `api/tests/data/`). A Cancel has its own identifier `<prefix>.<id>.cancel` and `references` the original. A CAP failure is logged and never blocks the phones | #37 |
| C-16 | Monorepo with npm workspaces (`dashboard` = `wildfire-dashboard`, `api` = `@wildfire/api`) and one root lockfile. `npm ci` at the root; `npx turbo dev` (or `make dev`) runs the API on :8000 and the dashboard on :5173; `npx turbo lint typecheck test build` runs every check with caching. `.venv` must exist first. Add dashboard packages with `npm install <pkg> --workspace dashboard` | #42 |
| C-17 | The dashboard polls `GET /health` every 5 s (10 s fetch timeout); unreachable is shown in words. `/health` and `/replay` are typed by hand in `src/api/client.ts` (no `response_model`). The alert log time is the last status change; sent and cancelled rows link to `cap.xml` | #41 |
| C-18 | Docker: `make docker-up` (= `docker compose up -d --build`) serves everything on `${PORT:-8000}`. `.env` read at runtime; `data/out` and `model/artifacts` mounted read-only, so new files need `docker compose restart`, not a rebuild. CI job `docker` builds the image | #40 |
| C-13 | `/predict` wind: request → Open-Meteo forecast (within `forecast.past_days` = 10 days) → ERA5 archive (older) → `weather_default`. Vector mean of the nearest hour and the next `forecast.mean_hours` (2), like the training feature `wind_speed_2h`. Cached per (lat, lon, hour) for 15 min; failures are not cached | #35 |
| C-19 | Terrain and fuel for any cell come from `core/static_raster.py` (`load`/`lookup`/`lookup_many`, `train.parquet` column names) reading `paths.static_raster` (`data/out/static_375m.npz`), built by `make static-raster` (resumable, `--shard i/4`, ~25 min whole bbox). One fire-style grid over `config.yaml → static_raster.bbox`. Only a 404 tile is sea. `rasterio` + `requests` are dev dependencies | #56 |
| C-21 | `ai_opinion` = model C's view of a village: likely (C's likely zone within 2 h), possible, unlikely (C ran for this pass, village outside both), null (no C for this fire). `GET /alerts?status=pending` orders by opinion, then `minutes_left` (null last). C never creates, drops or rejects a flag | #58 |
| C-22 | SSE queues hold `api.events_queue_size` (2000) events per client. An `/events` client that falls behind gets one `resync` event and must refetch `/alerts`; on `/alerts/stream` an overflow is only logged | #58 |
| C-20 | Model C's advice is violet (`mapColors.ai`/`aiOnDark`, CSS `--ai`): solid = likely, dashed = possible, 1 h thicker than 2 h. One toggle in the Layers card, disabled when `ai` is null. Times read "B: … · AI: …" (`fmtBothTimes`/`bothTimesParts` in `format.ts`) | #55 |

---

## 3. Decisions

### 3.1 Decided

| ID | Date | Decision | Rationale / notes |
| --- | --- | --- | --- |
| D-01 | 2026-11-20 | Work goes to the `dev` branch; `main` holds Scaffold v0.1 until the owner merges `dev` | Owner request |
| D-02 | 2026-11-20 | Standing authorization: the AI may commit, push, open PRs **and merge into `dev`** once CI is green, in dependency order. Never into `main` | Owner, workflow questions |
| D-03 | 2026-11-20 | Up to 4 parallel agents, each in its own worktree under `.claude/worktrees/` | Owner, workflow questions |
| D-04 | 2026-11-20 | Kit files are tracked in git. No Projects board: status comes from issue state, blocked-by links and open PRs | Owner, workflow questions |
| D-05 | 2026-11-20 | Minimal labels (phase + frontend/backend) and the issue body structure in C-04 | Owner request |
| D-06 | 2026-11-20 | No AI attribution in commits, PRs or issues | Kit default |
| D-07 | 2026-11-20 | Product pivot (spec v0.3): no mobile app. Dashboard + AI flags + operator approval + simulated cell broadcast (CAP) + risk map; planting demo in phase 3. Closed #2 #3 #13 #23 | Owner |
| D-08 | 2026-11-20 | Dashboard in React + TypeScript, with FastAPI integrating the AI (spec v0.3.1) | Owner |
| D-10 | 2026-11-20 | A manual `POST /alerts` is sent at once (the operator's click is the approval). Cancel applies only to sent alerts; a pending flag is rejected instead. The audit log records when, not who (one shared token) | #36 |
| D-11 | 2026-11-20 | #25 (approval queue) and #10 (phone page) start before the design mockups (#8): built from SPEC §6 with plain styling, restyled later | Owner, to get flag → approve → phone working sooner |
| D-12 | 2026-11-20 | Wave 3 builds #12 #21 #28 #29 against stub/fixture data (current placeholder texts, stub scoreboard, stub detections and risk cells, flagged `stub`); real data from #11 #4 #5 #19 #27 drops in later with no code change | Owner, nothing was unblocked |
| D-13 | 2026-11-20 | Dashboard UI follows DESIGN1 (light: paper/ink/fire, status words) + DESIGN2 (dark glass, map full-bleed, floating panels). Light/dark toggle (kept in the browser), map view Heatmap / 3D (Esri satellite imagery on terrain, tilted) / Normal (OpenFreeMap Liberty street map, both themes). Alert Log hidden from the Villages tab. Brand is "Hareeq" with the logos in `dashboard/public/`. Each fact has one home in the UI: receivers + data age in the status pill, connection problems in the top banners, layer toggles in the Layers card only, pending count on the Approval tab | Owner |
| D-14 | 2026-11-21 | Model C is advice next to B, not an alert maker: B creates every pending flag, C shows likely/possible zones and `ai_minutes_left`. Cross-validation (all Algerian fires): C better per cell (AUC 0.956 vs 0.896) but not yet per village, so B serves alerts | Owner, #51 #54 |
| D-15 | 2026-11-21 | The dashboard uses the Algeria Fire Map export instead of the stubs (`data/firedata/import_export.py`, `make import-export`). Until #27, `risk_today.parquet` is the export's `cell_risk.csv` (0.1° cells split onto the 0.05° display lattice; classes very-low/low→low, very-high/extreme→very_high; `top_factors` from the export's land cover, slope and fire history, not from a model) | Owner request |
| D-16 | 2026-11-21 | Q-05: model C trains on the static raster's terrain/fuel (`--terrain raster`), so training matches prediction time | #60 |
| D-09 | 2026-11-20 | If `OPERATOR_TOKEN` is unset, write endpoints stay open and log a warning (dev mode). If it is set, the header is required (401 otherwise). The demo sets it | Wave 1 seam, coordinator default |

### 3.2 Open (waiting on the owner)

| ID | Question | Default if unanswered | Raised |
| --- | --- | --- | --- |
| Q-01 | Civil Protection number in the alert texts | `[number, to confirm]` | 2026-11-20 |
| Q-02 | Export licence OK for a public repo? | Commerce checks before the pitch | 2026-11-20 |
| Q-03 | Darija and Kabyle script | Darija in Arabic script (RTL), Kabyle in Latin script | 2026-11-20 |
| Q-04 | "Plantable" definition from the Earth Engine layers; format of the 2002 dataset | Decided in #30 | 2026-11-20 |

---

## 4. Tasks waiting to be done

1. [x] Wave 1: #14, #24, #26, #32 merged into dev.
1. [x] Wave 2: #15, #39, #10, #25, #40 merged into dev.
2. [ ] Wave 3 waits on the human/data track below. First to unblock: #12 (needs #11), then #16 demo check.
3. [ ] Human / data track: #4 #5 #6 #17 (Electronics), #7 #19 #27 (AI), #8 (UI/UX), #11 (Commerce).

---

## 5. Milestone log

- 2026-11-21: Merged #63 #64 #65 #60; closed #18 #57. Wave 5 started (#58, #20); #58 merged (PR #66).
- 2026-11-20: Wave 2 complete: #10 phone page (PR #43), #25 approval queue (PR #44), #40 Docker (PR #45) merged.
- 2026-11-20: Wave 2: #15 status bar (PR #41) and #39 Turborepo (PR #42) merged; #25 and #10 started without mockups (D-11); #40 Docker started.
- 2026-11-20: Wave 1 done: #26 CAP (PR #37) and #32 React dashboard (PR #38) merged. Created #39 Turborepo and #40 Docker (owner request).
- 2026-11-20: #14 forecast wind (PR #35) and #24 approval API (PR #36) merged into dev.
- 2026-11-20: Kit adopted; issues #1–#33 created; spec v0.3.1; delivery started with wave 1.

---

## 6. Owner tasks

### Open
- **Turn on branch protection for `main`** (repo admin: maito-guy). Settings → Branches → require a PR and the `ci` check.
- **Confirm the repo being public is OK** before the data licence check (Q-02).
- **Set `OPERATOR_TOKEN` in `.env` on the demo laptop**, and tell the operator its value.
- **Tell the team chat about alert contract v0.2** (`source: auto` became `ai_spread`; new statuses `pending/rejected`; approve/reject endpoints; `/events`). It affects #25, #10, #26, #32.
- **Share the Drive folder** for `data/out/` and `model/artifacts/`, and pin its link in the team chat.

### Done
_None yet._

---

## 7. Notes and known issues

- Repo `maito-guy/wildfire-dz`; local clone `/home/malikou/Algeria2.0/wildfire-dz`. The owner's account `malek-bz09` has push but not admin.
- `gh` 2.45: no `--blocked-by`/`--parent` flags. Use `gh api repos/{o}/{r}/issues/N/dependencies/blocked_by -F issue_id=<id>`.
- The owner's token lacks the `project` scope (no board, by D-04).
- No `python3.11` on the owner's laptop, so `make setup` fails. Use uv (C-05).
- Open-Meteo: the forecast API returns `hourly.time` as `YYYY-MM-DDTHH:MM` UTC, plus parallel value arrays (checked live). The ERA5 archive lags about 5 days and was not checked live. When offline, each `/predict` without wind can wait up to the 3 s timeout.
- Never `pkill -f <pattern>` from a shell whose own command line contains the pattern: it kills that shell (exit 144). Kill by PID.
- On the stub grid, village labels overlap on the map (the design issue #8 may change them).
- The network drops sometimes. Retry `git push` and `gh` calls that fail with "no route to host" or "unexpected disconnect".
- CI runs on `pull_request` (any base) and on push to `main` only, not on push to `dev`.
- `scripts/merge-pr.sh` needs `gh pr update-branch`, which gh 2.45 lacks. Manual sequence: check the PR is based on the latest `origin/dev` (else merge `origin/dev` into the branch and push), wait for the `ci` run on the head SHA (`gh run list --workflow ci --commit <sha>`, then `gh run watch`), then `gh pr merge <n> --squash --subject "<title> (#<n>)" --body ""`.
- `Closes #N` does not auto-close issues on merges into `dev` (not the default branch). Close them by hand with a comment linking the PR.
- Headless UI check: `/usr/bin/google-chrome` + `playwright-core` installed in a scratch folder; use `waitUntil: 'load'` (the SSE stream keeps 'networkidle' from firing).
- GitHub runs no `pull_request` CI while a PR has merge conflicts: resolve first, then wait for the run on the new head SHA.
