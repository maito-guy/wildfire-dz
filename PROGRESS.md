# PROGRESS.md: Project memory store

This file is the single source of truth for the project's working state between
sessions: a current snapshot plus the decisions behind it. GitHub holds the
history. The rules for maintaining it are in `RULES.md` section 14. Keep
entries short and factual. Use absolute dates (YYYY-MM-DD).

**Last updated:** 2026-11-20

---

## 1. Current state

- **Phase:** delivery (`RULES.md`, `PROJECT_MANAGEMENT_RULES.md` §9–13). Spec: `SPEC.md` v0.3.1.
- **Running:** wave 1 (the agents and their issues are listed in §4).
- **Next up:** review and merge wave 1 PRs into `dev`, then wave 2 from the newly unblocked issues (#25, #26, #10).
- **Blockers:** data issues #4 #5 #6 #17 need the Algeria Fire Map export and a laptop run (Electronics); #8 #11 need humans (design, translations).

---

## 2. Conventions

| ID | Convention | Source |
| --- | --- | --- |
| C-01 | Integration branch is **`dev`**. Every issue branch starts from `origin/dev`, and every PR targets `dev`. `main` is updated from `dev` only by the owner | D-01 |
| C-02 | Branch names `<type>/<issue>-<slug>`, types `feat fix refactor docs test chore ci`. Conventional Commits with scopes `api`, `model`, `data`, `dashboard`, `alert`, `core`, `ci`, `docs` | kit §9 |
| C-03 | Labels: exactly one of `phase 1`, `phase 2`, `phase 3`, plus `frontend` or `backend`. No type, priority or status labels | D-05 |
| C-04 | Issue body sections: Owner · Why · User flow · What to build (In/Out) · Where · Done when · How to test · Depends on. Dependencies are real GitHub blocked-by links (REST API, because gh 2.45 has no `--blocked-by`) | D-05 |
| C-05 | Python 3.11. Setup: `uv venv -p 3.11 .venv && uv pip install -p .venv -r requirements-dev.txt` (or `make setup`). Checks: `.venv/bin/ruff check .` and `.venv/bin/python -m pytest -q`. In a worktree, use the main checkout's venv: `/home/malikou/Algeria2.0/wildfire-dz/.venv/bin/...` | scaffold |
| C-06 | Dashboard: React + TypeScript + Vite in `dashboard/`. Checks: `npm ci`, `npm run typecheck`, `npm run lint`, `npm run build`. FastAPI serves `dashboard/dist/` at `/dashboard/` | SPEC §3.1 |
| C-07 | Every threshold and path goes in `config.yaml`, never in code. `docs/contracts.md` and `api/schemas.py` change together, with a team-chat note | scaffold README |
| C-08 | SSE, not WebSocket: `/alerts/stream` (phones: sent alerts only) and `/events` (dashboard). Write endpoints take an `X-Operator-Token` header | SPEC §2, wave 1 seams |
| C-09 | CI workflow name is `ci`. Merge with `scripts/merge-pr.sh -w ci <pr>...` | kit |
| C-10 | Tests never call the real network; mock HTTP with `httpx.MockTransport` or monkeypatch | RULES §7.2 |

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

1. [ ] Wave 1 (agents): #32 React dashboard, #24 approval API, #14 forecast wind.
2. [ ] Wave 2 candidates once wave 1 merges: #26 CAP (after #24), #25 approval queue UI (after #24, #32, #8), #10 phone page (after #24, #8).
3. [ ] Human / data track: #4 #5 #6 #17 (Electronics), #7 #19 #27 (AI), #8 (UI/UX), #11 (Commerce).

---

## 5. Milestone log

- 2026-11-20: Kit adopted; issues #1–#33 created; spec v0.3.1; delivery started with wave 1.

---

## 6. Owner tasks

### Open
- **Turn on branch protection for `main`** (repo admin: maito-guy). Settings → Branches → require a PR and the `ci` check.
- **Confirm the repo being public is OK** before the data licence check (Q-02).
- **Share the Drive folder** for `data/out/` and `model/artifacts/`, and pin its link in the team chat.

### Done
_None yet._

---

## 7. Notes and known issues

- Repo `maito-guy/wildfire-dz`; local clone `/home/malikou/Algeria2.0/wildfire-dz`. The owner's account `malek-bz09` has push but not admin.
- `gh` 2.45: no `--blocked-by`/`--parent` flags. Use `gh api repos/{o}/{r}/issues/N/dependencies/blocked_by -F issue_id=<id>`.
- The owner's token lacks the `project` scope (no board, by D-04).
- No `python3.11` on the owner's laptop, so `make setup` fails. Use uv (C-05).
- The network drops sometimes. Retry `git push` and `gh` calls that fail with "no route to host" or "unexpected disconnect".
- CI runs on `pull_request` (any base) and on push to `main` only, not on push to `dev`.
