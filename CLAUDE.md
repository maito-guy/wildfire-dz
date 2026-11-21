# CLAUDE.md

Entry point for AI assistants working in this folder. Claude Code loads this
file automatically; the files below are imported so they are always in
context. (For other assistants, copy this file to `AGENTS.md`.)

## Start of every session

1. Read `PROGRESS.md`. Its section 1 says which phase the project is in.
2. Follow the rules for that phase (below). If `PROGRESS.md` and the folder
   disagree (for example `SPEC.md` exists but the phase says discovery), fix
   `PROGRESS.md` first.

## Phases

| Phase | Goal | Follow |
| --- | --- | --- |
| 1. Discovery | Interview the owner until `SPEC.md` is complete and approved | `DISCOVERY.md` |
| 2. Planning | Workflow decisions, repository, milestones, issues, dependencies, board | `PROJECT_MANAGEMENT_RULES.md` sections 3-8, 10.1 |
| 3. Delivery | Implement, verify, and merge issue by issue (parallel agents where possible) until every milestone is closed | `RULES.md`, `PROJECT_MANAGEMENT_RULES.md` sections 9-13 |
| 4. Done | Acceptance plan passed, docs match reality, final report given | `PROJECT_MANAGEMENT_RULES.md` section 13.2 step 6 |

A brand-new folder with only these kit files is in phase 1: greet the owner
and start the discovery interview.

## Required reading

1. @PROGRESS.md: the project memory store (current phase and state,
   conventions, decisions, next steps, owner tasks, environment notes).
   **Keep it updated** (`RULES.md` section 14).
2. @DISCOVERY.md: how to turn the idea into `SPEC.md`.
3. @RULES.md: how to plan, write, test, and report on work.
4. @PROJECT_MANAGEMENT_RULES.md: how to manage GitHub (issues, milestones,
   labels, dependencies, branches, PRs, parallel agents, delivery loop) with `gh`.
5. `SPEC.md` (once it exists): the product specification. Read the relevant
   sections before planning or implementing anything.

When delegating issues to subagents, give them `SUBAGENT_BRIEF.md`
(`PROJECT_MANAGEMENT_RULES.md` section 9.3). Changes to the kit files
(`CLAUDE.md`, `DISCOVERY.md`, `RULES.md`, `PROJECT_MANAGEMENT_RULES.md`,
`SUBAGENT_BRIEF.md`) are proposed to the owner and made only with their
approval (`PROJECT_MANAGEMENT_RULES.md` section 13.1).

## Precedence

1. Explicit instructions from the owner in the current conversation.
2. Decisions recorded in `PROGRESS.md` and in the spec's decisions log.
3. `SPEC.md`.
4. `DISCOVERY.md`, `RULES.md`, and `PROJECT_MANAGEMENT_RULES.md`.

When two sources conflict and the precedence above does not settle it, ask the
owner and record the answer in `PROGRESS.md`.
