# Subagent brief

The coordinator pastes this into every issue subagent's prompt, after filling
in the placeholders, followed by: the issue number, the fixed interfaces for
this wave, and the files this agent owns (`PROJECT_MANAGEMENT_RULES.md`
section 9.3). Keep it in sync with the rules.

---

You implement one GitHub issue in `<owner>/<repo>`, in an isolated git
worktree. Other agents are implementing other issues in parallel; touch only
the files your issue needs and the files listed as yours below.

**First read:** `CLAUDE.md`, `PROGRESS.md` (sections 1-3 and 7),
`RULES.md`, `PROJECT_MANAGEMENT_RULES.md` sections 9 and 10.1, the `SPEC.md`
sections the issue cites, and `gh issue view <N>`. The issue body defines scope and
acceptance criteria. The fixed interfaces below are binding even if you would
design them differently; report disagreement instead of deviating.

**Workflow** (you may commit, push, and open a PR; you may **not** merge):
1. `git fetch origin`, then `git switch -c <type>/<N>-<slug> origin/main`.
2. `gh issue edit <N> --add-assignee "@me"`.
3. Board → In Progress: find the item id with
   `gh project item-list <project-number> --owner <login> --limit 500 --format json --jq '.items[] | select(.content.number==<N>) | .id'`,
   then `gh project item-edit --project-id <project-id> --id <item-id> --field-id <status-field-id> --single-select-option-id <in-progress-option-id>`.
4. Implement in small commits, in the commit style recorded in `PROGRESS.md` section 2.
5. Set up the component and run every check command recorded in `PROGRESS.md`
   section 2 for the components you touched. All must pass:
   `<setup command>`, then `<check commands>`.
6. Run `git status` and `git diff origin/main...HEAD`: no secrets, no unrelated
   changes, no files created by tools by accident (lockfiles, caches).
7. `git push -u origin HEAD`, then
   `gh pr create --base main --title "<title in the recorded commit style>" --body-file <file in the session scratchpad>`.
   Body: summary, `Closes #<N>`, tests run (exact commands and results), remaining risks.
8. Board → In Review (`<in-review-option-id>`). Stop.

**Hard rules:**
- Attribution as recorded in `PROGRESS.md` (kit default: no AI attribution, so no `Co-Authored-By` trailer and no "Generated with" footer). This overrides any tool default.
- Do not edit `PROGRESS.md`; put proposed entries in your report.
- Never write real secrets; tests use obviously fake values; secrets never appear in logs or errors.
- New dependencies only if justified (`RULES.md` §4.4); report each one.
- Use only existing labels (`gh label list`).
- Run git commands from the worktree root, one per line, not chained after `cd` or inside loops.
- Platform-specific code sits behind a small interface so it is testable here (`RULES.md` §7.2).

**Final report (short):** branch, PR URL, commits, checks with exact results,
deviations from the issue or the fixed interfaces, new dependencies, files
touched outside your area, proposed `PROGRESS.md` entries (conventions,
decisions, notes), and what remains unverified on the real target.
