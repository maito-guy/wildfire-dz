# AI Coding Rules

These rules define how an AI assistant plans, changes, verifies, and reports on
work in this repository. They apply from the planning phase on; the discovery
phase (turning an idea into a spec) follows `DISCOVERY.md`. GitHub project
management (issues, milestones, labels, branches, PRs, parallel agents) is
covered in `PROJECT_MANAGEMENT_RULES.md`. Project state and memory live in
`PROGRESS.md` (section 14).

These rules assume no language, framework, platform, or tool. Every
project-specific choice (stack, check commands, conventions) is decided with
the owner and recorded in the spec or in `PROGRESS.md`, never assumed from a
previous project.

## 1. Core principles

1. **Understand before changing.** Inspect the relevant code, structure,
   documentation, configuration, and tests before proposing or making changes.
2. **Follow the project, not personal preferences.** Match the existing
   architecture, conventions, formatting, naming, dependencies, and supported
   versions unless the task explicitly calls for changing them. Project
   conventions are listed in `PROGRESS.md` section 2.
3. **Prefer simple, maintainable solutions.** Choose the smallest design that
   fully solves the problem. Avoid speculative abstractions, unnecessary
   layers, premature optimization, and unrelated refactoring.
4. **Preserve existing behavior.** Do not silently change public APIs, data
   formats, user-facing behavior, or compatibility guarantees.
5. **Make assumptions visible.** If a requirement is ambiguous and the choice
   could materially affect the result, ask a focused question and record it in
   `PROGRESS.md` section 3.2. Otherwise make a reasonable assumption, state it,
   and record it as a decision.
6. **Be accurate.** Never claim that code was run, tested, reviewed, or
   verified unless it actually was.
7. **Remember across sessions.** Start every session by reading `PROGRESS.md`,
   and end every session (or finished task) by updating it.
8. **Reach the real target early.** Code for an environment the AI cannot run
   locally (another OS, a service account, real hardware, a third-party
   service) is not proven by unit tests. Exercise it on the real system as soon
   as a thin slice exists, not only at the end (section 7.3).

## 2. Planning

Before implementing a non-trivial task:

1. Restate the desired outcome and identify the constraints, including the
   spec sections and `PROGRESS.md` decisions that apply.
2. Inspect the existing implementation and find the actual entry points and
   dependencies involved.
3. Find related tests, interfaces, callers, documentation, and configuration.
4. Identify edge cases, failure modes, security implications, and
   compatibility concerns.
5. Break the work into small, ordered steps.
6. Decide how each important behavior will be verified, and where (locally, in
   CI, or on the real target).

Keep the plan proportional to the task:
- For a small, local change, use a short plan or proceed directly.
- For a multi-file or architectural change, present a clear plan before editing.
- Do not write elaborate plans for routine changes.

Do not start implementing from filenames or assumptions when the relevant code
can be inspected.

When several Ready issues are independent, they can be implemented in
parallel by subagents. Follow `PROJECT_MANAGEMENT_RULES.md` section 9.3: fix
the shared interfaces first, brief each agent with `SUBAGENT_BRIEF.md`, give
each its own worktree, and let one coordinating session review, merge, and
update `PROGRESS.md`.

## 3. Repository exploration

- Read the relevant files before editing them.
- Search for existing implementations before adding new ones.
- Trace important call paths and data flow instead of looking at a function in isolation.
- Check how nearby code handles errors, logging, configuration, and dependency injection.
- Find the project's build, test, lint, and formatting commands (section 7.1).
- Prefer existing libraries and utilities over adding new dependencies.
- Do not inspect or change unrelated areas without a reason.

## 4. Implementation

### 4.1 General

- Write code that is clear, explicit, and easy to maintain.
- Keep functions and modules focused on one responsibility.
- Use descriptive names that communicate intent.
- Avoid duplicated logic, but do not introduce abstractions for code that is only superficially similar.
- Keep control flow straightforward. Avoid clever tricks and unnecessary indirection.
- Handle errors explicitly and keep useful error context.
- Validate inputs at the appropriate boundaries.
- Keep configuration separate from business logic; load it in one place.
- Avoid hidden global state and unnecessary mutable state.
- Make time, randomness, and external I/O injectable where tests need to control them.
- Write comments that explain *why* something is done, not what the code already says.
- Do not leave dead code, temporary debugging output, commented-out implementations, or unused imports.
- Do not add TODOs in place of finishing the requested work. Genuinely deferred
  work goes into a GitHub issue; work that needs the owner goes into
  `PROGRESS.md` section 6.

### 4.2 Language and platform specifics

The spec names the stack; the planning phase turns it into conventions in
`PROGRESS.md` section 2: language and version, project layout, concurrency
rules, how configuration is loaded, and platform constraints. Follow the
idioms of the chosen ecosystem, and record a convention whenever a choice is
made that the next session would otherwise have to rediscover.

### 4.3 Scope control

- Make only the changes the task requires, plus closely related fixes.
- Do not reformat or rewrite unrelated files.
- Do not rename public symbols, move modules, or change interfaces without a clear need.
- Avoid changing dependency versions unless required.
- If you find a broader improvement, propose it as an issue rather than silently expanding the task.

### 4.4 Dependencies

Before adding a dependency:
1. Check whether the project already has a suitable dependency or a standard-library solution.
2. Confirm that it supports the project's language, runtime, and target platforms.
3. Consider maintenance, licensing, security, size, and operational cost.
4. Explain why it is justified, and record it as a decision in `PROGRESS.md`.

Do not add a dependency for a trivial utility function.

## 5. Correctness and edge cases

Consider, where relevant:

- Empty, missing, malformed, and boundary inputs.
- Invalid state transitions and unexpected call order.
- Duplicate requests or repeated operations; idempotency.
- Time zones, timeouts, cancellation, and concurrency.
- Resource cleanup and file/connection lifecycle.
- Partial failures and retries (never retry non-idempotent requests blindly).
- Numeric limits, overflow, precision, and rounding.
- Backward compatibility and existing persisted data.
- Platform and runtime differences (operating system, service accounts,
  container vs host, shell differences, network stack behavior).

Do not add defensive code everywhere. Validate at meaningful boundaries and
handle realistic failure cases.

## 6. Security and privacy

- Treat external input, files, network responses, and environment variables as untrusted.
- Never hardcode credentials, tokens, private keys, or other secrets.
- Make sure `.gitignore` excludes secret-bearing files (`.env`, local configs)
  **before** the first commit that could include them. Only examples with
  placeholder values are committed.
- Never ask the owner to paste secrets into the chat, and never write secrets
  into `PROGRESS.md`, issues, PRs, commit messages, or logs.
- When the AI handles a secret itself (generating it, copying it to another machine), it never prints it:
  - Generate it straight into its destination file, or on the machine that uses it.
  - Move it between machines through a pipe (`grep … .env | cut … | ssh host '<read stdin>'`), never as a visible argument or echoed output.
  - Check a secret by its shape only (length, character classes, separators). This catches the common mistake of pasting the wrong kind of credential (a client secret where a token was expected, an id where a key was expected).
  - Clear shell variables that held it, and restrict secret-bearing files to the account that needs them.
- Do not log passwords, tokens, sensitive personal data, or full confidential payloads.
- Use parameterized queries for database access.
- Apply authorization checks on the server side; never rely on UI restrictions.
- Compare secrets in constant time.
- Validate file paths and prevent path traversal where applicable.
- Avoid unsafe deserialization, shell injection, and insecure defaults. Never build shell commands from external input.
- Code that runs with elevated privileges never resolves programs through a
  search path or the working directory; use absolute paths.
- Use established cryptographic libraries and protocols; do not invent cryptography.
- Check exposure on the real deployment, not only in code: a service bound to
  all interfaces can be reachable through an unrelated firewall or proxy rule.
  Verify from outside that only the intended endpoints answer.
- Ask for confirmation before destructive actions or changes to production systems.
- Do not weaken authentication, authorization, TLS, validation, or other security controls to make tests pass.

## 7. Tests and verification

### 7.1 Commands

Use the check commands recorded in `PROGRESS.md` section 2 (formatter, linter,
type checker, tests, build). Record them during planning; CI must run the same
commands.

### 7.2 Rules

- Add or update tests for changed behavior.
- Prefer tests that verify observable behavior over implementation details.
- Cover the main success path and meaningful failure or boundary cases.
- Keep tests deterministic. Do not depend on real external services unless the
  test is explicitly an integration test. Fake the clock for timers.
- Use mocks and fakes only where they improve isolation. Do not mock the behavior the test is supposed to verify.
- Platform-specific code sits behind a small interface so its callers can be
  tested anywhere. Tests that need the real platform are marked and skipped
  elsewhere.
- Do not encode platform timing or ordering assumptions in tests; the same
  operation can take milliseconds on one platform and seconds on another.
- Run the narrowest relevant tests first, then broader checks when practical.
- Inspect the final diff for accidental changes, missing files, generated artifacts, and secrets.

If a check cannot be run, say exactly which check was skipped and why. Report
failures honestly; never describe failing tests as passing. Checks that only
the owner can run are listed as owner tasks in `PROGRESS.md` section 6.

### 7.3 Verification on the real target

Unit tests and CI run in one environment; the product runs in another (a
server, a device, a browser, a third-party service, a user's machine). First
contact with the real environment typically finds problems in minutes that no
unit test could: version differences, timing, permissions, what an external
system actually returns or logs. Therefore:

- As soon as a component can run, run it once on the real target (deploy it,
  run the test suite there, call the real service), even if the formal
  verification issue comes later.
- Before writing an acceptance criterion that depends on how an external system
  behaves ("X appears in its log", "the API returns Y"), check that behavior on
  the real system. If it cannot be checked yet, mark it as an assumption.
- Every problem found in the real environment gets its own issue, a fix, and a
  line in `PROGRESS.md` section 7 so the next session knows the quirk.
- Prefer direct evidence of the state you care about over indirect signals
  that can fail for unrelated reasons.
- Scripts that wait for real-world state changes poll for the **final** state
  with a deadline, print timestamps, and never assume they will observe an
  intermediate state: a fast transition can finish between two polls.
- Run long real-world tests as background scripts that log to a file, so an
  interrupted session can read the result afterwards.

## 8. APIs, data, and compatibility

- Follow existing API and schema conventions. Change a cross-component contract
  only by updating the spec (or recording a decision) together with every side.
- Treat public interfaces and persisted data as compatibility boundaries.
- Prefer additive, backward-compatible changes when possible.
- Consider validation and error responses for API changes.
- For database changes, consider existing data, migration order, rollback, and deployment compatibility.
- Do not hand-edit generated files that can be regenerated from their source.

## 9. Documentation

Update documentation when a change affects:
- Setup, installation, or configuration.
- Public APIs or user-visible behavior.
- Environment variables, permissions, or operational procedures (runbook, example config files).
- Architecture or important design decisions (the spec, and `PROGRESS.md` section 3).

After the first real installation, add every problem it hit to the runbook's
troubleshooting section: symptom, cause, fix. Keep documentation consistent
with the implementation; do not add documentation that only repeats the code.

## 10. Tool and command use

- Prefer read-only inspection commands before commands that change state.
- Explain potentially destructive commands before running them.
- Do not delete, overwrite, reset, migrate, publish, deploy, or change production data without explicit authorization.
- Do not run broad cleanup commands to solve a narrow issue. Delete by explicit name, not by wildcard.
- Respect the repository's package manager, build system, and lockfiles.
- Never assume a command succeeded; inspect its result. In a chain joined by
  `&&`, one failing step silently skips the rest: check that every step ran
  before acting on the last one's output.
- Put temporary files (issue bodies, scratch scripts) outside the repository, in the session scratchpad.
- Run `git status` after running tools in the repository. Tools create files on
  their own (lockfiles, caches); remove the ones you created by accident and
  never commit them.

### 10.1 The owner's machines and accounts

The owner may give the AI access beyond the repository (a shell on another
machine, a cloud account, an API token). Record each grant as a decision in
`PROGRESS.md`, then:

- **Ask before changing the system.** Reading state needs no approval.
  Installing software, changing network or security settings, services,
  scheduled jobs, restarts, users and permissions need the owner's yes,
  preferably in one question that lists every change. Editing an application's
  own config as part of an approved task is allowed, after a timestamped backup.
- **Never cut off your own session.** Before restarting or disconnecting
  anything, check what the AI session itself runs through, and move the session
  somewhere that stays up first.
- **Credentials stay with the owner.** Ask the owner to perform logins and
  type passwords themselves, in a way the AI can then reuse without seeing the
  secret (for example a shared SSH master connection, or a CLI already logged
  in). For commands that need elevation, give the owner the exact command.
- **Know the remote environment.** Check the shell, OS, and tool versions
  before writing commands for it; record them in `PROGRESS.md` section 7.
- **Clean up.** Remove temporary jobs, logs, and copied files, and say what was
  left behind on purpose.
- **Verify from the outside**, and **record access**: how to reach each
  machine or account goes in `PROGRESS.md` section 7.

## 11. Working with Git

- Keep the owner's uncommitted changes. Never discard, reset, stash, or overwrite them without permission.
- Inspect `git status` and the relevant diff before editing.
- Do not commit, push, open pull requests, merge, or publish releases unless
  the owner asked for it in the current conversation **or** a standing
  authorization is recorded in `PROGRESS.md` section 3.1. Approval for one
  action does not extend to unrelated ones
  (`PROJECT_MANAGEMENT_RULES.md` section 13.1).
- Follow the branch and commit conventions in `PROJECT_MANAGEMENT_RULES.md` section 9.
- Keep changes focused and reviewable: one issue per branch and PR.
- Do not amend commits, rewrite history, force-push, or change branches unless
  explicitly requested or required by the authorized workflow.

## 12. Communication

While working:
- Give short progress updates on substantial tasks.
- During long operations (CI waits, installs, remote tests), say in one line what is running before going quiet.
- Explain important design choices and trade-offs.
- Ask only the questions needed to avoid a materially wrong result. Batch them.
- Do not ask again for information already in the repository, `PROGRESS.md`, or the conversation.
- When the owner must act, give the exact copy-paste command, say where to run it, and say what you will do with the result.
- Warn before anything that interrupts the owner: a reboot, a dropped connection, a service restart.
- If an instruction contains an apparent slip (an address that belongs to a
  different machine, a name that does not exist), point it out and use the
  evident intent instead of following the slip.

When finishing, report:
1. **What changed:** a summary of the implementation.
2. **Why:** important design decisions, where useful.
3. **Verification:** the checks actually run, with results, and where they ran.
4. **Limitations:** skipped checks, known risks, or follow-up work.
5. **Owner actions:** any new owner tasks added to `PROGRESS.md` section 6.

Keep the summary factual and concise, with file paths. Do not claim completion
while part of the task remains unfinished.

## 13. Definition of done

A task is complete when:

- The requested behavior is implemented.
- The implementation follows the project's conventions and stays in scope.
- Relevant tests are added or updated.
- Appropriate checks have been run, or skipped checks are clearly disclosed.
- Behavior that depends on a real target has been exercised there, or the gap is recorded as an owner task.
- Documentation is updated where needed.
- The diff contains no accidental or unrelated changes.
- `PROGRESS.md` is updated (section 14).
- Related GitHub issues and PRs reflect the real state (`PROJECT_MANAGEMENT_RULES.md` section 14).
- Remaining assumptions, limitations, and risks are communicated.

## 14. PROGRESS.md: the project memory store

`PROGRESS.md` is the persistent memory between sessions. Conversation history
is not memory; anything that must survive goes in this file. It is a **current
snapshot plus the decisions behind it**, not a diary: GitHub (issues, PRs,
commits) is the history.

### 14.1 When to read it

- At the start of every session, before planning or editing anything. Read
  section 1 first; if it disagrees with GitHub or the repository, the file is
  stale: fix it before working.
- Before making a decision: check whether it was already made (section 3) or is already a convention (section 2).
- Before asking the owner a question: check whether it was already asked or answered.
- After a context reset or summary inside a session: re-read it rather than trusting the summary.

### 14.2 What each section holds

| Section | Holds | Does not hold | Size |
| --- | --- | --- | --- |
| 1 Current state | Phase, next step, blockers, what is deployed and running | History | At most ~8 lines; rewritten as a whole, never appended to |
| 2 Conventions | Rules the code and process follow, with the module or file to read | API documentation (that is the code and the spec) | One or two lines per row |
| 3.1 Decided | Owner choices and deviations from the spec, with date and rationale | Things any reader can derive from the code | One row each |
| 3.2 Open | Questions waiting on the owner, each with a default | | |
| 4 Waiting | The next few steps in order, linking issues | The full backlog (GitHub) | ~5 items |
| 5 Milestone log | One line per milestone or major event | Every closed issue or PR (GitHub has them) | One line per event |
| 6 Owner tasks | Open steps that need the owner, with exact commands; finished ones as one-line results | Long logs of what was done | Done items are collapsed |
| 7 Notes | Facts that are true now: environment quirks, ids, access helpers, gotchas | Facts that stopped being true | One line each |

### 14.3 When to update it

Update it as part of the work, not as an afterthought:

| Event | Section | What to write |
| --- | --- | --- |
| A convention is established (naming, tooling, commands, structure) | 2 | New row `C-xx` with its source |
| The owner makes a choice, or a spec assumption is confirmed or overridden | 3.1 | New row `D-xx` with date and rationale; remove it from 3.2 |
| A question needs the owner's answer | 3.2 | New row with the question, the proposed default, and the date |
| New work is identified | GitHub, then 4 if it is next | Open an issue; section 4 only links it |
| A milestone closes, or a major event happens (first deploy, backlog created) | 5 | One line with the date |
| The AI cannot do something (section 14.5) | 6 | A checkbox with exact, copy-pasteable instructions |
| An owner task is done | 6 | Tick it, collapse it to one line with the result, and move any lasting fact to 3.1 or 7 |
| A quirk, gotcha, or failed approach is learned | 7 | One line |
| A note stops being true | 7 | Rewrite or delete it in the same commit that changes the reality |
| The phase, next step, blockers, or deployment change | 1 | Rewrite the whole section |

Always update the **Last updated** date at the top. Commits that touch only
`PROGRESS.md` may go straight to `main` with a `docs:` message
(`PROJECT_MANAGEMENT_RULES.md` section 9.1); everything else goes through a PR.
If the owner keeps the AI files out of git (README, "Tracked or local"), just
save the file; there is nothing to commit.

When several agents work in parallel, only the coordinating session edits
`PROGRESS.md`. Subagents report proposed entries in their final message.

### 14.4 Writing rules

- Short and factual. One line per item where possible. Absolute dates (YYYY-MM-DD).
- IDs (`C-xx`, `D-xx`) are never reused or renumbered, so other documents can
  refer to them. New rows are appended with the next free number.
- A reversed decision gets a new row that says which one it supersedes; the old
  row gets "(superseded by D-yy)". Do not delete decision history.
- Do not copy what the spec, the code, or git history already records. Link to it.
- Never write secrets. Non-secret identifiers (IDs, LAN addresses, hostnames) are fine.
- Do not record temporary authorizations the owner gives "for this session
  only". They live in the conversation. Record only standing authorizations.
- Before ending a session, check: section 1 matches reality, no note in section
  7 is false, every finished owner task is collapsed, and the date is current.

### 14.5 Owner tasks

Anything the AI cannot or must not do itself goes into `PROGRESS.md`
section 6 as a task for the owner. This includes:
- Actions on hardware or systems the AI has no access to.
- Third-party web consoles (developer portals, router admin pages, cloud consoles) without an API the AI may use.
- Typing passwords, interactive logins, and anything requiring the owner's credentials.
- Real-world checks (using the product as a real user, anything physical).
- Decisions only the owner can make (also listed in section 3.2).

"Cannot" depends on the access the AI has. When the owner grants access (SSH,
a group membership, an API token in a file), re-check every open owner task:
the AI does what it now can, says who did each step ("by the AI over SSH"),
and leaves the rest with the owner. Generating secrets is not in itself an
owner task, as long as section 6 is followed.

Each task is a checkbox with exact steps or commands, the reason it is needed,
and, if it blocks code work, the issue or milestone it blocks. Use `[ ]` for
open and `[x]` for done; a partly done task stays `[ ]` and says what is left.
Point out new owner tasks in the end-of-task report (section 12).

------------------------------------------------------------------------

## Priority rule

If these rules conflict with an explicit user requirement, follow the user's
requirement unless doing so would create a security, privacy, legal, or
destructive-action risk. Precedence between project documents is defined in
`CLAUDE.md`: user instructions, then `PROGRESS.md` decisions, then the spec,
then these rules and `PROJECT_MANAGEMENT_RULES.md`. If more specific
repository instructions exist (`AGENTS.md`, `CONTRIBUTING.md`, package-level
guidance), follow them as long as they do not conflict with higher-priority
instructions.
