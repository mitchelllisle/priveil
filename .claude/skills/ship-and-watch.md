---
name: ship-and-watch
description: >
  Opens a pull request with the GitHub CLI, then watches it to completion.
  Polls CI checks, review approval, and review-thread resolution on a loop
  until every gate is green. Gates on unresolved review threads — not just
  CHANGES_REQUESTED. Merges only when all three gates are green, then writes
  a summary. Use when asked to "ship and watch", "ship it", "raise the PR and
  merge when green", or to create, monitor, and merge a pull request.
argument-hint: "[base-branch]"
---

# Ship and Watch

A PR is mergeable only when **all three gates** are satisfied:

1. **Checks** — every required CI run has passed.
2. **Approval** — at least one approving review.
3. **Comments resolved** — every review thread is resolved (use GraphQL, not `reviewDecision`).

## Step 0 — Pre-flight

```bash
gh auth status
git rev-parse --abbrev-ref HEAD   # must be a feature branch, not base
git status --porcelain            # must be clean
```

Push if needed: `git push -u origin HEAD`

## Step 1 — Open the PR

```bash
git log --oneline "$(gh repo view --json defaultBranchRef -q .defaultBranchRef.name)..HEAD"
gh pr create --base "<base>" --head "$(git rev-parse --abbrev-ref HEAD)" \
  --title "<imperative title>" --body "<what changed and why>"
PR=$(gh pr view --json number -q .number)
OPEN_SHA=$(git rev-parse HEAD)
```

## Step 2 — Watch loop (poll all three gates each round)

**Gate A — Checks:** `gh pr checks "$PR"` — exit 0 = pass, exit 8 = pending, exit 1 = STOP.

**Gate B — Approval:** read `reviewDecision` from `gh pr view "$PR" --json reviewDecision`.
- `APPROVED` → green. `null` → ask user before merging. `REVIEW_REQUIRED` / `CHANGES_REQUESTED` → keep polling.

**Gate C — Unresolved threads (GraphQL):**
```bash
gh api graphql -F owner='<owner>' -F repo='<repo>' -F pr="$PR" -f query='
  query($owner:String!, $repo:String!, $pr:Int!) {
    repository(owner:$owner, name:$repo) {
      pullRequest(number:$pr) {
        reviewThreads(first:100) {
          nodes { isResolved isOutdated path comments(first:1) { nodes { author { login } body } } }
        }
      }
    }
  }' | jq '[.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved==false)] | length'
```

Merge only when count == 0. Never assume `isOutdated == true` means resolved — confirm the fix, then resolve.

## Step 3 — Merge

When A + C green and `mergeable != CONFLICTING`:
- `APPROVED` → `gh pr merge "$PR" --squash --delete-branch`
- `null` → prompt user first; wait for explicit yes.

## Step 4 — Ship report

```bash
git log --oneline "$OPEN_SHA"..HEAD
git diff --stat "$OPEN_SHA"..HEAD
gh pr view "$PR" --json reviews,comments
gh api "repos/<owner>/<repo>/pulls/$PR/comments"
```

Report: what changed after the PR opened, each piece of feedback and its resolution, final gate status.

## Hard stops

- Gate A exit 1 (check failed).
- Gate C count > 0 (unresolved threads).
- `mergeable == CONFLICTING`.
- 20 polling rounds elapsed — report and hand back.
