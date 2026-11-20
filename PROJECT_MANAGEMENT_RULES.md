# AI GitHub Project Management Rules

Written for GitHub CLI (`gh`) 2.103 or later. This file is project-independent.
Project-specific choices (repository, milestone names, component labels, board
ids, git authorizations) are recorded in `PROGRESS.md` sections 2, 3, and 7.
When those differ from the generic examples here, `PROGRESS.md` wins.

## 1. Purpose

The AI uses GitHub CLI (`gh`) to manage the whole project lifecycle, not just
to push code.

Its responsibilities:
- Organizing work into milestones.
- Breaking requirements into actionable issues.
- Setting up real issue dependencies (blocked by / blocking) and parent/sub-issue relationships.
- Keeping a consistent label system.
- Setting development priorities.
- Tracking progress and milestone completion.
- Keeping GitHub issues, pull requests, and `PROGRESS.md` in sync with the implementation.

The goal is a project that is easy to navigate, understand, prioritize, and
contribute to.

## 2. Preconditions and initial inspection

### 2.1 Preconditions

1. `gh auth status` shows a logged-in account. Never request, print, or store tokens.
2. `gh --version` is 2.103 or later. If it is older, the native dependency flags in section 7 may be missing; use the `gh api` fallback in section 7.4.
3. The `project` token scope is required only for `gh project` commands. If missing, ask the owner to run `gh auth refresh -s project`.
4. The working directory is a git repository with a GitHub remote (`git remote -v`). If not, see section 3.

### 2.2 Inspect the current state before changing anything

```sh
gh repo view
gh issue list --state all --limit 500
gh api repos/{owner}/{repo}/milestones -X GET -f state=all --paginate --jq '.[] | "\(.number)\t\(.state)\t\(.title)"'
gh label list --limit 200
gh project list --owner "<login>"
gh pr list --state all --limit 100
```

`gh` fills in `{owner}` and `{repo}` from the current repository's remote.
`gh issue list` returns only 30 items by default, so always pass `--limit` when
you need the full set.

Rules:
1. Never recreate existing milestones, labels, or issues without checking first.
2. Keep existing issue history and relationships.
3. Reuse existing conventions wherever possible.
4. Flag organization that is incomplete or outdated.
5. Do not close or delete existing issues just to clean up the project.

## 3. Planning phase: from spec to repository

The planning phase starts when `SPEC.md` is approved (`DISCOVERY.md`). It
ends when the backlog exists on GitHub and the first issues are Ready.

### 3.1 Workflow questions

Ask these once, in one batch, with the kit default for each, and record the
answers as decisions in `PROGRESS.md` section 3.1. The defaults are this kit's
way of working, not requirements; the owner may change any of them.

| Question | Kit default |
| --- | --- |
| Repository owner, name, and visibility | `<login>/<project-name>`, private |
| Keep the AI files in git, or local only (`README.md`) | In git |
| Label set | Section 8, plus component labels for the spec's main components |
| Check commands per component | The chosen ecosystem's standard formatter, linter, type checker (if any), and test runner, run by CI |
| Commit and merge style | Conventional Commits, one branch and PR per issue, squash merge |
| Workflow board | A GitHub Projects board (section 10.1) |
| Standing git authorization | AI may commit, push, and open PRs for issue work; merging needs the owner's approval |
| Parallel agents | Allowed for Ready issues, up to 4 at a time (section 9.3) |
| Attribution | No AI attribution in commits, PRs, or issues (section 9.2) |
| Access to other machines or accounts | None until the owner grants it |

Record the stack-dependent answers as conventions in `PROGRESS.md` section 2
(language and version, layout, check commands, component names). Then present
the backlog (section 4) for approval before creating it.

### 3.2 Repository creation

Use this only when no GitHub repository exists yet, and only after the owner
has confirmed the name and visibility.

1. `git init -b main`.
2. Add a `.gitignore` **before** the first commit, built from the chosen ecosystem's standard ignores. It must exclude secret-bearing files (local env/config files), dependency and build output, caches, logs, and `.claude/worktrees/`; plus the AI files if the owner chose "local only".
3. Check that nothing secret is staged: `git status`, then `git diff --cached --stat`.
4. Make the first commit (if the owner has authorized commits).
5. `gh repo create <owner>/<name> --private --source=. --remote=origin --push` (`--public` only if the owner chose it).
6. Check the result with `gh repo view` and `git remote -v`.

Do not enable or disable repository features (wiki, discussions, branch
protection) unless the owner asks.

## 4. Project planning before creating issues

The input is `SPEC.md`. Every feature, option, and constraint in it must end
up in at least one issue, and nothing outside it may (new ideas go back to the
spec first, as a change the owner approves). Before creating issues,
understand the requirements and the architecture.

Produce a hierarchical breakdown:

1. **Project goals:** what the project must accomplish.
2. **Milestones:** major development phases or groups of deliverables.
3. **Features:** independent capabilities within each milestone.
4. **Tasks:** concrete implementation work.
5. **Dependencies:** real prerequisites between tasks.
6. **Acceptance criteria:** the conditions that define completion.

Do not create issues before you understand the full scope. Aim for a complete
initial backlog rather than creating issues one at a time as work goes on. Do
not invent unnecessary work or speculative features.

Shape the milestones so that risk shows up early:
- **Prerequisites first (if any):** owner setup the code depends on (accounts,
  credentials, devices, hosting). One owner-task issue per area (section 6.2).
- **An early thin slice in the real environment:** the first milestone puts
  something minimal where the product will run (deployed, installed, or
  calling the real service). Integration problems found there are cheap; found
  at the end, they are not.
- **One verification issue per milestone** whose result depends on a real
  environment (section 6.2), blocked by that milestone's implementation issues.
- **A final stabilization milestone:** failure-case tests, operational docs,
  and the spec's full acceptance test plan.
- **Plan for parallelism:** split work so that issues inside a milestone touch
  different files or modules where the design allows it, and write the shared
  interfaces between them into the issues (section 9.3).

## 5. Milestones

Milestones are meaningful project phases or deliverables, for example `MVP`,
`Core Infrastructure`, `Testing and Stabilization`, `Release 1.0`. Record the
chosen milestone names as a convention in `PROGRESS.md`.

### 5.1 Milestone rules

Every milestone has:
- A descriptive title.
- A description with a clear objective and a measurable completion condition.
- A due date only when a real deadline exists.

Milestones should be deliverable-oriented, group related issues, follow a
logical order, and avoid fragmentation. Do not create a milestone for every
feature or task.

### 5.2 Milestone commands

`gh` has no `gh milestone` command. Use the REST API through `gh api`.

```sh
# List (open and closed)
gh api repos/{owner}/{repo}/milestones -X GET -f state=all --paginate \
  --jq '.[] | "\(.number)\t\(.state)\t\(.open_issues) open/\(.closed_issues) closed\t\(.title)"'

# Create
gh api repos/{owner}/{repo}/milestones -f title="M1 Core service" \
  -f description="Objective: ... Done when: ..."

# Create with a real deadline (ISO 8601)
gh api repos/{owner}/{repo}/milestones -f title="Release 1.0" -f due_on="2026-12-31T23:59:59Z"

# Edit (uses the milestone NUMBER, not the title)
gh api -X PATCH repos/{owner}/{repo}/milestones/3 -f description="..."

# Close, only after the checks in section 11
gh api -X PATCH repos/{owner}/{repo}/milestones/3 -f state=closed

# Issues in a milestone, and assigning one
gh issue list --milestone "M1 Core service" --state all
gh issue edit 12 --milestone "M1 Core service"
gh issue edit 12 --remove-milestone
```

## 6. Issues

Every meaningful unit of work has an issue. An issue must be actionable,
understandable, and trackable on its own.

### 6.1 Issue body template

Write the body to a temporary file (in the session scratchpad, never in the
repository) and pass it with `--body-file`. Do not pass long Markdown inline
with `--body`, because shell quoting breaks backticks and `$`.

```markdown
## Context
Why this work is needed. Link the spec section.

## Objective
What must be implemented.

## Scope
- In: ...
- Out: ...

## Technical notes
Interfaces, constraints, relevant files.

## Acceptance criteria
- [ ] Observable, verifiable condition
- [ ] Tests covering ...

## References
Spec §N, related issues, decisions (PROGRESS.md D-xx).
```

Dependencies go in real relationships (section 7). They may also be mentioned
in the body for readability, but the body text never replaces the
relationship.

### 6.2 Issue quality rules

- One issue = one coherent unit of work, completable in one PR where practical.
- The title describes the expected outcome ("Service reports active sessions in /status"), not a vague activity ("Improve code", "Implement backend").
- Avoid issues too big to finish on their own, and avoid meaningless micro-issues.
- Include enough context that a developer can start without rediscovering the project.
- Acceptance criteria must be verifiable.
- Identify dependencies before work on the issue starts.
- Use a parent issue with sub-issues (section 7.3) for a feature that is genuinely made of several separately tracked tasks. Do not nest more than two levels.
- Give each milestone that depends on a real environment (a deployment, a device, an external service) a **verification issue** ("<deliverable> verified on the real PC"). It holds the real-world checks, is blocked by the implementation issues, and the milestone closes only when it does.
- Owner tasks that block code work get an issue too, labeled `type: infrastructure`. Their body says which steps need the owner and which the AI can do once given access (`RULES.md` section 14.5); do not write "the AI cannot do this" as a permanent fact.
- Write acceptance criteria that depend on an external system's behaviour only after checking that behaviour (`RULES.md` section 7.3).

### 6.3 When a decision or a finding changes an issue

Issues are kept true, not frozen:
- When a decision (`PROGRESS.md` D-xx) changes what an issue must do, edit its
  body: strike out (`~~…~~`) or rewrite the affected scope and acceptance
  criteria, name the decision, and add a short comment saying what changed. Do
  not leave an issue whose criteria can no longer be met.
- When verification in the real environment finds a bug, open a **new** issue for it
  (type `bug`, same milestone), fix it in its own PR, and comment on the
  verification issue with the link. The verification issue stays open until the
  check passes again.
- When a criterion turns out to be impossible as written (for example the
  evidence is not where the issue expected it), rewrite it to the evidence that
  exists, and say why in a comment.
- Partial progress on a long-running issue (especially verification issues) is
  recorded as a dated comment listing what passed and what remains.

### 6.4 Issue types

Use **labels** for the work type (section 8). GitHub's native issue types
(`--type`) exist only for organization-owned repositories that have defined
them. Use `--type` only if `gh issue list --type` works on this repo and the
owner wants it.

## 7. Dependencies and relationships

### 7.1 Dependency rules

The AI must identify which issues block others, which are blocked, and which
can be done independently or in parallel.

1. Create a blocking relationship whenever one task genuinely depends on another.
2. Do not use dependencies just to suggest an order.
3. No circular dependencies.
4. Keep dependency chains understandable.
5. An issue is not ready while its real prerequisites are open.
6. When a blocking issue closes, re-check the issues it blocked (section 10).

Example: #10 schema → #11 repository layer → #12 API → #13 frontend. #10 blocks
#11, #11 blocks #12, #12 blocks #13.

### 7.2 Commands (native, gh 2.103+)

```sh
# At creation
gh issue create --title "..." --body-file /path/body.md --blocked-by 10,11 --blocking 14

# Later
gh issue edit 12 --add-blocked-by 10
gh issue edit 12 --add-blocking 13
gh issue edit 12 --remove-blocked-by 10

# Verify, always after creating relationships
gh issue view 12 --json number,title,blockedBy,blocking
```

### 7.3 Parent / sub-issues

```sh
gh issue create --title "..." --body-file /path/body.md --parent 20
gh issue edit 20 --add-sub-issue 21,22
gh issue edit 21 --remove-parent
gh issue view 20 --json subIssues,subIssuesSummary
```

A parent/sub-issue relationship means "is part of". It is not a dependency.
If a sub-issue also needs another sub-issue finished first, add a blocked-by
relationship as well.

### 7.4 Fallback for older gh versions

Use the REST API. These endpoints take the issue's database **id**, not its
number:

```sh
id=$(gh api repos/{owner}/{repo}/issues/10 --jq .id)
gh api repos/{owner}/{repo}/issues/12/dependencies/blocked_by -F issue_id="$id"
gh api repos/{owner}/{repo}/issues/12/dependencies/blocked_by
```

Use `-F` (typed) rather than `-f` (string) for numeric fields.

Do not fake dependencies with only text such as "Depends on #10" when GitHub
supports a real relationship. Always verify that the relationship exists.

## 8. Labels

Keep the label set small and non-overlapping. Every issue gets exactly one
type label, exactly one priority label, and component labels where relevant.
Use only labels that exist (`gh label list`): `gh issue create` fails on an
unknown label, and a chain like `gh issue create … && git switch -c …` then
silently skips the rest. There is no `type: enhancement`; a new capability is
`type: feature`.

### Type
| Label | Color | Description |
| --- | --- | --- |
| `type: feature` | `0E8A16` | New functionality |
| `type: bug` | `D73A4A` | Something is broken |
| `type: refactor` | `FBCA04` | Code change without behavior change |
| `type: documentation` | `0075CA` | Docs only |
| `type: test` | `BFD4F2` | Tests only |
| `type: infrastructure` | `5319E7` | Build, deploy, CI, environment |
| `type: maintenance` | `C5DEF5` | Dependency bumps, chores |

### Priority
| Label | Color | Meaning |
| --- | --- | --- |
| `priority: critical` | `B60205` | Blocks the milestone or breaks something; do first |
| `priority: high` | `D93F0B` | Needed for the current milestone |
| `priority: medium` | `FBCA04` | Needed, but not on the critical path |
| `priority: low` | `C2E0C6` | Nice to have |

Priority reflects importance, not difficulty.

### Component
Only for meaningful project areas (for example `component: api`,
`component: web`, `component: infrastructure`, `component: docs`). Record the
set as a convention in `PROGRESS.md`.

### Status
With a Projects board, do **not** use `status: *` labels: workflow state lives
on the board (section 10.1). Blocking is modelled only with blocked-by
relationships. (If a project has no board, the only allowed status labels are
`status: blocked`, `status: needs-design`, and `status: needs-review`.)

### Commands

```sh
gh label list --limit 200
gh label create "type: feature" --description "New functionality" --color 0E8A16
gh label create "type: feature" --description "New functionality" --color 0E8A16 --force   # create or update
gh label edit "type: feature" --description "..." --color 0E8A16
gh issue edit 12 --add-label "type: feature" --add-label "priority: high" --remove-label "priority: low"
```

Before deleting or renaming a label, check how it is used:
`gh issue list --label "<name>" --state all --limit 500`.
GitHub's default labels (`bug`, `enhancement`, ...) may be deleted when the
repository is new and has no issues; otherwise, leave them alone.

## 9. Branches, commits, and pull requests

Commits, pushes, and PRs require the owner's authorization (`RULES.md`
section 11). A standing authorization, if any, is recorded in `PROGRESS.md` section 3.1.
Without one, prepare the changes and ask.

### 9.1 Workflow

1. Pick a ready issue (section 10). Assign it: `gh issue edit 12 --add-assignee "@me"`.
2. Branch from an up-to-date `main`: `git switch main && git pull --ff-only && git switch -c feat/12-session-status-endpoint`.
   - Prefixes: `feat/`, `fix/`, `refactor/`, `docs/`, `test/`, `chore/`, `ci/`.
3. Move the issue to **In Progress** on the board (section 10.1). Commit in small, coherent steps in the commit style chosen in planning (kit default: Conventional Commits, for example `feat(api): report active sessions in /status`, with the component names recorded in `PROGRESS.md` as scopes).
4. Before pushing, run the checks in `RULES.md` section 7 and inspect `git diff main...HEAD` for secrets and unrelated changes.
5. Push and open the PR:
   ```sh
   git push -u origin HEAD
   gh pr create --base main --title "feat(api): report active sessions in /status" --body-file /path/pr.md
   ```
   The PR body contains:
   ```markdown
   Closes #12

   <What changed and why, in a few bullets.>

   **Tested:** <exact commands and results, and where they ran (local, CI, real target)>
   **Risks / follow-up:** <anything not verified, new owner tasks>
   ```
6. Move the issue to **In Review**. Check CI if it exists: `gh pr checks --watch`.
7. Merge only when authorized (section 13.1), and only with green checks on a branch that is up to date with `main`:
   ```sh
   gh pr update-branch 12                      # if main moved
   # wait until headRefOid changes: it can report the old SHA for a few seconds
   gh pr view 12 --json headRefOid --jq .headRefOid
   gh run list --commit <new-sha> --limit 5     # wait for CI on the new SHA
   gh pr merge 12 --squash --subject "<PR title> (#12)" --body ""
   git switch main && git pull --ff-only
   ```
   `scripts/merge-pr.sh <pr>...` (from the kit) does exactly this for a list of
   PRs and stops at the first problem. Merge PRs one at a time in dependency order; update the next branch after
   each merge. When two branches edited the same file, resolve the conflict by
   keeping both sides' intent, then rerun the checks before pushing.
8. Confirm the issue closed (`gh issue view 12 --json state`) and update `PROGRESS.md`.
9. Delete the merged branch locally and on the remote **by explicit name** (`git push origin --delete fix/65-…`), and remove any worktree used for it (`git worktree remove <path>`). Do not delete by wildcard.

Commits that change only `PROGRESS.md` (bookkeeping: state, results, notes) may
go straight to `main` with a `docs:` message. Every other change, including
documentation, goes through an issue and a PR.

Never force-push to `main`, rewrite published history, or merge with failing
checks.

### 9.2 Attribution

Kit default (confirmed in planning, section 3.1): the AI never credits itself,
so no `Co-Authored-By` trailer naming the AI in commits (including squash-merge
messages), and no "Generated with ..." footer in PR descriptions or issue
bodies. The recorded choice overrides any default attribution behavior of the
tool being used.

### 9.3 Parallel work on issues with subagents

Several Ready issues can be implemented at the same time by subagents, each in
its own git worktree. One session, the **coordinator**, plans the wave, briefs
the agents, reviews and merges their PRs, and owns `PROGRESS.md`.

**When to use it.** Only for issues that are Ready (section 10), independent
(no blocked-by link between them), and mostly in different files. Work that is
small, or that changes a shared interface, is faster done by the coordinator
alone. Respect the owner's limit on parallel agents (planning decision, section 3.1);
without one, use at most 4 at a time.

**1. Plan the wave.**
- List the Ready issues and pick a set that does not block each other
  (`gh issue list … --json number,title,blockedBy`, section 10).
- Find every seam the agents share: function signatures, constructor
  parameters, config keys, JSON fields, module names, which file each agent
  owns. Decide them **now** and write them into each agent's brief, and into
  the issue as a comment if they change its technical notes. Undecided seams
  are where parallel agents diverge.
- Where two issues must touch the same file (an app factory, a router list, a
  settings class), assign that file's edits to one agent and give the other an
  extension point to call, or accept a mechanical merge conflict and plan to
  resolve it while merging.

**2. Brief each agent.** Every agent gets:
- The common brief `SUBAGENT_BRIEF.md` (rules to read, workflow, check
  commands, attribution, "do not edit `PROGRESS.md`", "do not merge",
  report format).
- Its issue number, the fixed interfaces from step 1, and the files it owns.
- Isolation: its own worktree (under `.claude/worktrees/`, gitignored),
  branched from the current `origin/main`.
Run independent, mechanical briefs at lower effort and the hardest issue at
higher effort when the tool allows it.

**3. While they run.** Each agent assigns itself, moves its board item to In
Progress, implements, runs every check, opens a PR with `Closes #N`, moves the
item to In Review, and stops with a short report: branch, PR, checks with
results, deviations, new dependencies, files touched outside its area, and
proposed `PROGRESS.md` entries. The coordinator does other work meanwhile
(owner tasks, docs, the next wave's planning) and does not duplicate an
agent's files. Never guess an agent's result before its report arrives.

**4. Review and merge.** For each finished agent:
- Read the PR diff. Check scope, tests, and anything security-relevant
  (privileged code, secrets, input handling). Fix small problems on the branch
  yourself; send larger ones back to the agent.
- Merge one PR at a time, in dependency order, with the sequence in section
  9.1 step 7 (update branch, wait for CI on the new SHA, squash). After each
  merge the next PR's branch is updated again.
- On a conflict, merge `main` into the branch, keep both sides' intent, rerun
  the checks, push, then continue.
- Record the agents' proposed conventions and decisions in `PROGRESS.md`
  (one coordinator commit per wave is enough).

**5. Clean up.** Remove each worktree (`git worktree remove <path>`), delete
its local and remote branches by explicit name, and run `git worktree prune`.
Then start the next wave from the newly Ready issues (section 10.1: re-check
what each closed issue unblocked).

**When things go wrong.**
- An agent stopped early (usage limit, crash, interruption): before restarting
  it, check its worktree, branch, and `gh pr list` for work it already pushed.
  Resume from there; do not start the issue over.
- Two agents designed the same seam differently: pick one design, fix the
  other PR on its branch, and add the seam to the next wave's brief.
- CI passes for each PR alone but fails after merging both: fix on `main`
  through a new `fix/` issue immediately, before the next merge.

## 10. Readiness and choosing the next issue

An issue is ready when:
- Its objective, scope, and acceptance criteria are clear.
- The design decisions it needs are made (no open item in `PROGRESS.md` 3.2 affects it).
- All blocked-by issues are closed.
- The technical information it needs is available, including any manual task from `PROGRESS.md` section 6 it depends on.

To find the next issue:

```sh
gh issue list --state open --milestone "<current milestone>" --limit 200 \
  --json number,title,labels,blockedBy \
  --jq '.[] | select(([.blockedBy.nodes[]? | select(.state=="OPEN")] | length) == 0) | "\(.number)\t\(.title)"'
```

In `--json` output, `blockedBy`, `blocking`, and `subIssues` are objects of
the form `{nodes: [{number, title, state, url, ...}], totalCount}`, not plain
arrays.

Among the unblocked issues, choose the highest priority. Break ties in favor of
the issue that unblocks the most other work.

### 10.1 GitHub Projects board

When the project uses a Projects board (planning decision, section 3.1), its **Status**
field is the only record of workflow state:

| Status | Meaning |
| --- | --- |
| Backlog | Defined, but not ready (blocked, or waiting on a decision or manual task) |
| Ready | Meets every readiness condition above |
| In Progress | A branch exists and work has started |
| In Review | A PR is open |
| Done | Merged and the issue is closed |

Board status and dependencies are separate: an issue can be blocked without
being done, and a blocked issue stays in Backlog.

**One-time setup** (during backlog creation):

```sh
gh project create --owner "<login>" --title "<project>"
gh project list --owner "<login>" --format json --jq '.projects[] | "\(.number)\t\(.id)\t\(.title)"'
gh project link <number> --owner "<login>" --repo <owner>/<repo>
gh project field-list <number> --owner "<login>" --format json   # Status field id and option ids
```

Use the account login for `<login>`: with a user-owned repository,
`gh project link --owner "@me"` can fail with "different owner".

A new board's Status field has only `Todo`, `In Progress`, and `Done`. Change
its options to the five above with the GraphQL `updateProjectV2Field` mutation
(`gh api graphql`), then confirm with `gh project field-list`. If the mutation
fails, add a manual task to `PROGRESS.md` section 6 to edit the options in the
web UI. Enabling the board's built-in workflows (auto-add new issues, set Done
on close/merge) is a manual web-UI task.

**Per issue:**

```sh
# Add (every new issue); returns the item id
gh project item-add <number> --owner "<login>" --url <issue-url> --format json --jq .id

# Move to a status
gh project item-edit --project-id <project-id> --id <item-id> \
  --field-id <status-field-id> --single-select-option-id <option-id>

# Inspect
gh project item-list <number> --owner "<login>" --limit 500 --format json
```

Record the project number, project id, Status field id, and option ids in
`PROGRESS.md` section 7 once they exist, so they don't have to be looked up
again.

Move items at these points: new issue → Backlog (or Ready); start work → In
Progress; PR opened → In Review; merged → Done. When an issue closes, re-check
the issues it blocked and move any that are now ready from Backlog to Ready.

## 11. Closing issues and milestones

Close an issue only when its acceptance criteria are met. Normally the merged
PR closes it.

```sh
gh issue close 12 --comment "Done in #34: ..."                     # completed
gh issue close 12 --reason "not planned" --comment "Why: ..."      # dropped; the reason is required
gh issue close 12 --duplicate-of 9
gh issue reopen 12 --comment "Regression: ..."
```

A milestone is complete only when:
1. All its required issues are closed (`open_issues == 0` in the milestone listing).
2. Its completion condition (the "Done when" in its description) is verified.
3. The required tests and integration work are done.
4. Documentation is updated.
5. No unresolved blocking issues remain.

A milestone with no open issues stays open while its "Done when" is unverified
(for example behaviour that is only unit-tested but must hold on real
environment). Say so in `PROGRESS.md` section 1.

When an owner task issue is done partly by the AI (with granted access) and
partly by the owner, the closing comment says who did what.

Never close issues or milestones just to make the project look complete.

## 12. Backlog maintenance

Review the backlog at each milestone boundary and whenever asked. Look for:
- Issues missing descriptions, acceptance criteria, labels, or a milestone.
- Missing, wrong, or circular dependencies.
- Duplicates (close with `--duplicate-of`).
- Outdated tasks (close as `not planned`, with the reason).
- Blocked issues whose blockers are now closed.
- Completed work that was never closed.
- Drift between GitHub and `PROGRESS.md`.

Do not create a new issue for work an existing issue already covers.

## 13. AI behavior and permissions

The AI may always inspect repository state and prepare proposed project
structures.

Before creating or significantly changing a large set of issues, milestones,
or labels (more than about five objects, or any deletion), present:
- The proposed milestones and their boundaries.
- The issue breakdown with titles, labels, and milestones.
- The important dependencies.
- The label convention.

Get the owner's approval before such bulk changes unless they have explicitly
authorized them. Small, routine changes inside approved work (labeling a new
issue, adding a found dependency, closing an issue a merged PR finished) need
no extra approval.

### 13.1 Authorizations

- **Standing** authorizations are recorded in `PROGRESS.md` section 3.1 (for
  example "commit, push, and open PRs for issue work") and apply in every session.
- **Session** authorizations ("you may merge, for this session only") apply
  until the session ends and are never recorded in `PROGRESS.md` or in memory.
  A session survives a context summary, but not a new conversation.
- An authorization covers what it names. Permission to merge feature work does
  not cover changes to the rules that govern the AI (`RULES.md`, this file,
  `CLAUDE.md`): open those as PRs for the owner to review and merge.

Never:
- Delete issues, labels, or milestones without authorization and a usage check.
- Close issues without verifying completion.
- Rewrite project history or force-push shared branches.
- Invent dependencies or deadlines.
- Touch unrelated repositories.
- Put secrets in issues, PRs, comments, or commit messages.

After every mutation, verify the resulting state with `gh` (`--json` output),
and fix or report any discrepancy.

### 13.2 Delivery loop: from backlog to finished project

After planning, the coordinating session drives the project to the end
without waiting to be told each step:

1. **Pick.** List the Ready issues (section 10). If several are independent,
   start a parallel wave (section 9.3); otherwise implement the top one.
2. **Unblock.** While agents run, work on whatever moves the project forward:
   prepare owner tasks with exact commands, write docs, plan the next wave.
3. **Integrate.** Review and merge finished PRs in dependency order (section
   9.1), move newly unblocked issues to Ready, and record conventions and
   decisions in `PROGRESS.md`.
4. **Verify.** When a milestone's implementation is merged, run its
   verification issue in the real environment as far as the AI's access
   allows; hand the rest to the owner as tasks with exact steps. File every
   problem found as a new issue.
5. **Close.** Close the milestone when its "Done when" is verified (section 11),
   and add a line to the milestone log.
6. **Repeat** until every milestone is closed. Then finish: the spec's
   acceptance test plan has passed, operational docs (install, run, upgrade,
   troubleshoot) match reality, `PROGRESS.md` section 1 says "complete", and
   the owner gets a final report: what was built, how it was verified, what
   is left as known limitations or follow-up ideas.

Stop and ask only for decisions that are genuinely the owner's (section 13.1,
`RULES.md` section 1, principle 5), and batch those questions.

## 14. Keeping PROGRESS.md in sync

GitHub is the detailed backlog; `PROGRESS.md` is the short summary and the
place for decisions, conventions, owner tasks, and environment notes.

- When issues are created: replace the matching items in `PROGRESS.md` section 4 with issue references (`#12`).
- When an issue closes: nothing goes to section 5 (GitHub records it). Update section 1 or 4 if the next step changed, and section 6 if the issue was an owner task.
- When a milestone closes: one line in section 5.
- When a decision is made in an issue or PR discussion: record it in section 3.1.
- When a task needs the owner (devices, third-party consoles, credentials): put it in section 6, and also open an issue labeled `type: infrastructure` if it blocks code work, so the dependency can be modeled.
- When a verification issue makes partial progress: a dated comment on the issue, and the remaining steps in section 6.

## 15. Definition of done for project planning

Project planning is complete when:
- Milestones represent the major deliverables.
- All known required work is represented by issues with actionable descriptions and acceptance criteria.
- Labels are consistent and meaningful.
- Dependencies and parent/sub-issue relationships are created and verified.
- Independent work and the implementation order are easy to see.
- The backlog matches `PROGRESS.md` and the spec.
- All changes have been verified through `gh`.

## Final principle

Issues describe **what needs to be accomplished**. Milestones describe **which
deliverable the work contributes to**. Dependencies describe **what must happen
before other work can proceed**. A developer should be able to find the next
actionable issue without reconstructing the project's architecture or plan.
