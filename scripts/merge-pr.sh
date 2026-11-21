#!/usr/bin/env bash
# Merge PRs one at a time, safely:
#   for each PR: update its branch to the base, wait until GitHub reports the
#   new head SHA, wait for the CI workflow on that SHA, then squash-merge with
#   the subject "<PR title> (#N)" and an empty body.
# Stops at the first problem and says why.
#
# Usage: scripts/merge-pr.sh [-w <workflow name>] <pr> [<pr>...]
#   Run from inside the repository. Default workflow name: CI.
#   PRs are merged in the order given, so list them in dependency order.
set -u

workflow="CI"
if [ "${1:-}" = "-w" ]; then
  workflow="$2"
  shift 2
fi
[ $# -gt 0 ] || { echo "usage: $0 [-w <workflow>] <pr>..." >&2; exit 2; }

for pr in "$@"; do
  title=$(gh pr view "$pr" --json title --jq .title) || { echo "STOP $pr: cannot read PR"; exit 1; }
  old=$(gh pr view "$pr" --json headRefOid --jq .headRefOid)

  if ! upd=$(gh pr update-branch "$pr" 2>&1); then
    state=$(gh pr view "$pr" --json mergeStateStatus --jq .mergeStateStatus)
    [ "$state" = "CLEAN" ] || { echo "STOP $pr: update-branch failed (state=$state): $upd"; exit 1; }
  fi

  # After update-branch, headRefOid can report the old SHA for a few seconds.
  sha=$old
  if ! grep -qi "already up-to-date\|up to date" <<<"$upd"; then
    for _ in $(seq 1 30); do
      sha=$(gh pr view "$pr" --json headRefOid --jq .headRefOid)
      [ "$sha" != "$old" ] && break
      sleep 3
    done
    [ "$sha" != "$old" ] || { echo "STOP $pr: head SHA did not change after update-branch"; exit 1; }
  fi

  run=""
  for _ in $(seq 1 60); do
    run=$(gh run list --workflow "$workflow" --commit "$sha" --json databaseId --jq '.[0].databaseId // empty')
    [ -n "$run" ] && break
    sleep 5
  done
  [ -n "$run" ] || { echo "STOP $pr: no '$workflow' run for $sha"; exit 1; }

  gh run watch "$run" --exit-status >/dev/null 2>&1 || { echo "STOP $pr: CI failed (run $run)"; exit 1; }
  gh pr merge "$pr" --squash --subject "$title (#$pr)" --body "" >/dev/null || { echo "STOP $pr: merge failed"; exit 1; }
  echo "MERGED $pr ($title), CI run $run"
done
echo DONE
