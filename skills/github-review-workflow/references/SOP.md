# GitHub Review SOP

## Purpose

Turn a GitHub PR URL into a clean local queue of review threads plus separate
CodeRabbit outside-diff and nitpick queues, then triage the full bundle up
front, address accepted stacked-review fixes in a new top-of-stack PR, and post
accurate review-thread replies as the GitHub ledger of what was handled.

This reference lives inside the skill. The bundled scripts generate review
bundles under `.github-review-workflow/` in the current project.

The workflow exists to avoid these failure modes:

- treating summary reviews as the action queue
- blindly implementing every bot suggestion
- pushing partial fixes that repeatedly retrigger review automation
- amending older PR branches in a stack and forcing downstream rebase churn
- losing track of deferred review replies while waiting for a follow-up PR URL

## Queues

Inline review threads are the main action queue. CodeRabbit outside-diff
comments are exported separately because GitHub could not place them inline;
triage them after thread-backed `todo/` items and before lower-priority
nitpicks. CodeRabbit nitpicks are exported separately, triaged up front, and
lower priority by default. Summary review wrappers are context, not work items.

## Bundle Layout

Each PR exports to `.github-review-workflow/pr-<number>-<slug>/`.

Expected files:

- `README.md`: local export snapshot and index for the bundle
- `manifest.json`: machine-readable export snapshot metadata
- `context/01-coderabbit-walkthrough.md`: optional top-level context
- `todo/`: review items not yet handled
- `outside-diff/`: CodeRabbit outside-diff review-summary items; actionable but
  not thread-backed
- `nitpicks/`: CodeRabbit nitpick summary items, lower priority than `todo/`
- `done/`: accepted, implemented, audited, and replied to when thread-backed
- `ignored/`: declined after merit, scope, or audit review, and replied to when
  thread-backed
- `../reply-queue/`: global durable JSON drafts for GitHub review-thread replies

Thread-backed review item files include the IDs needed for follow-up replies.
Outside-diff and nitpick files are not GitHub review threads and must not use
the bundled follow-up or reply-queue scripts. Do not delete review files; folder
placement is the status record.

## Export

Run scripts by their path inside this skill directory. Do not run
`python3 scripts/...` from the project root unless that happens to be the skill
directory. Set `SKILL_DIR` to this skill's installed or repo-local path.

```bash
python3 "$SKILL_DIR/scripts/export_github_review_comments.py" \
  https://github.com/<owner>/<repo>/pull/<number>
```

Useful flags:

- `--include-ai-prompts` preserves embedded `Prompt for AI Agents` sections;
  they are stripped by default
- `--include-resolved` includes already-resolved inline review threads
- `--out-root <path>` writes bundles somewhere other than
  `.github-review-workflow/`

Re-running the exporter preserves recognized local status placement and adds
newly discovered inline threads to `todo/`, outside-diff comments to
`outside-diff/`, and nitpicks to `nitpicks/`.

After export, open:

- `$SKILL_DIR/references/SOP.md`
- `.github-review-workflow/pr-<number>-<slug>/README.md`
- `.github-review-workflow/pr-<number>-<slug>/context/01-coderabbit-walkthrough.md` if it exists
- all files in `.github-review-workflow/pr-<number>-<slug>/todo/`
- all files in `.github-review-workflow/pr-<number>-<slug>/outside-diff/` if it exists;
  triage them as local-only items because GitHub could not place them inline
- all files in `.github-review-workflow/pr-<number>-<slug>/nitpicks/` if it exists;
  triage them as lower-priority local-only items unless the user asked to
  handle them now

## Initial Triage

Before editing, read the full local bundle. Build one queue-level view before
choosing any fixes:

- provisionally accepted items
- provisionally ignored items
- related groups that should be fixed together
- likely files touched
- dependencies or ordering constraints
- items worth delegating

Global triage is for context, deduplication, grouping, and ordering. Execution
must still happen in bounded, auditable work units rather than as one large
undifferentiated change.

## Stack-Aware Base

Before editing, make sure you are on the right local base for the fixes. For
stacked PR review-comment cleanup, the right base is the current top of the
stack, not the branch that originally received the comment.

Run this preflight before editing:

```bash
reviewed_pr=<url-or-number>

git status --short --branch
git fetch origin --prune

gh pr view "$reviewed_pr" \
  --json number,title,url,state,headRefName,baseRefName,headRefOid,isDraft,mergeStateStatus

gh pr list --state open --limit 100 \
  --json number,title,url,headRefName,baseRefName,isDraft,updatedAt,mergeStateStatus \
  --jq '.[] | "#\(.number) \(.headRefName) -> \(.baseRefName) [\(.mergeStateStatus)] \(.url)"'
```

Use the reviewed PR's `headRefName` as the starting branch. In the open PR
list, follow PRs whose `baseRefName` equals the current branch in that walk:
exactly one child means continue to that child's `headRefName`; zero children
means the current branch in the walk is the stack top; multiple children means
the stack is ambiguous, so stop and ask which branch or worktree should receive
the fix. Use the detected stack top as `fix_base`.

Default branch behavior:

- do not amend, rebase, force-push, or otherwise update older reviewed PR
  branches for review-comment fixes
- if the reviewed PR is lower in the stack, put accepted fixes on a new branch
  from the current top-of-stack branch and create a new PR above it when the
  user asked for stacked review follow-through
- if the reviewed PR is not part of a stack and the user did not ask for PR
  follow-through, keep code changes local and use the direct follow-up script
- if the current branch is not the intended local base, ask before switching
  branches unless the user already made the target branch clear
- if the correct local base is ambiguous, stop and ask the user which branch or
  worktree should receive the fix

This is an intentional exception to the normal stacked-diffs maintenance rule
that earlier diffs may be updated and downstream branches rebased. For review
comment cleanup on an active stack, avoid rebase churn and put the correction in
a follow-up PR above the current stack top.

Create the follow-up branch and PR from the detected stack top with explicit
base and head values; do not rely on `gh pr create` guessing from the current
checkout:

```bash
fix_base=<top-of-stack-branch>
fix_branch=<new-review-fix-branch>

git fetch origin "$fix_base"
git switch -c "$fix_branch" "origin/$fix_base"

# Implement the accepted fixes, then audit as described in Reply Queue Lifecycle.
git add <changed-files>
git commit -m "<message>"
git push -u origin "$fix_branch"

gh pr create \
  --base "$fix_base" \
  --head "$fix_branch" \
  --title "<title>" \
  --body "<body>"

fix_pr=<fix-pr-url-or-number>
gh pr view "$fix_pr" \
  --json number,url,baseRefName,headRefName,mergeStateStatus,changedFiles,additions,deletions
gh pr diff "$fix_pr" --name-only
gh pr diff "$fix_pr" --patch
```

After creation, verify `baseRefName` matches `fix_base`, `headRefName` matches
`fix_branch`, and the PR diff contains only the intended review fixes before
posting fixed replies.

## Review Loop

Handle `todo/` before `outside-diff/`, and `outside-diff/` before `nitpicks/`,
unless the user explicitly asks otherwise.
Use the initial triage to choose bounded work units: one review item, or a
small related group.

For each work unit:

1. Inspect the referenced code directly.
2. Reassess merit before changing code.
3. Implement small, obvious fixes directly.
4. Delegate only if the work unit is large, complex, multi-file, risky, or
   benefits from isolated investigation.
5. If delegating, give the worker only the bounded work unit, relevant context
   files, relevant item files, and implementation constraints. Do not hand over
   the full queue.
6. Audit the final diff yourself, including worker output.
7. Audit the relevant diff/status before queueing a reply. Do not stage changes
   unless preparing the explicit follow-up PR.
8. For each thread-backed item in the work unit, create a durable reply draft:
   - accepted stacked fix: queue `fixed`; reply is blocked until the fix PR URL
     exists
   - ignored, declined, or obsolete: queue `declined`; reply can post
     immediately or with the next queue flush
9. Move local item files only after the required reply succeeds:
   - `done/` for accepted fixes implemented, audited, visible in the follow-up
     PR, and replied to
   - `ignored/` for items not taken after merit, scope, or audit review, with
     the reason replied to on GitHub

Do not resolve GitHub threads as part of the default loop. If reply posting
fails, leave the item in `todo/`, report the blocker, and do not mark it `done/`
or `ignored/`. If a reply posts but moving the local item fails, rerun the queue
post command; it must move the file without reposting the reply.

## Outside-Diff Loop

Read and triage `outside-diff/` during the initial bundle pass. Execute them
after `todo/` is empty or when the user explicitly asks to handle them. These
are CodeRabbit review-summary items that could not become inline GitHub review
threads, so they are local-only by default:

- inspect the referenced code directly
- apply the same merit gate as thread-backed comments
- do not call the bundled follow-up script
- move accepted outside-diff items to `done/` after local audit
- move declined outside-diff items to `ignored/` after recording the reason
- do not post a GitHub reply unless explicitly requested
- if the user wants a public ledger, prefer one manual summary comment using
  the `Review URL` for context

## Nitpick Loop

Read and triage `nitpicks/` during the initial bundle pass. Execute them only
after `todo/` and `outside-diff/` are empty or when the user explicitly asks to
handle nitpicks.
Apply the same merit gate, but remember that these files do not represent
GitHub review threads:

- inspect the referenced code directly
- ignore stylistic churn aggressively
- make only small, clearly justified fixes
- do not call the bundled follow-up script
- move accepted nitpicks to `done/` after local audit
- move declined nitpicks to `ignored/` after recording the reason
- do not post a GitHub reply unless explicitly requested
- if the user wants a public ledger for nitpicks, prefer one manual summary
  comment, not the bundled follow-up script, over per-nitpick replies; use the
  `Review URL` for context

## Merit Gate

Take comments that improve correctness, safety, accessibility, maintainability,
or factual clarity with proportional complexity. Decline stylistic churn,
speculative abstractions, defensive code without local evidence, renames that do
not clarify, and tests that only restate the implementation. When in doubt,
prefer the simpler change or no change.

## Delegation

The orchestrator owns the queue. Workers are optional and should be used only
when overhead is justified: nontrivial investigation, several files, meaningful
test design, risky changes, or several comments pointing to one shared issue.
Handle typo, docs, naming, simple correctness, simple test updates, mechanical
edits, and low-merit suggestions directly.

A delegated work unit should be small enough to review completely and large
enough to avoid duplicated setup cost. Prefer one related group over several
near-duplicate workers. Never hand the whole queue to one worker.

When delegating, give the worker only the context needed for that bounded work
unit:

- `context/01-coderabbit-walkthrough.md` if relevant
- the assigned review item files
- specific implementation constraints discovered during triage

Workers must reassess merit, make the smallest defensible fix if valid, avoid
unrelated files, and leave final status-folder movement to the orchestrator.

## Reply Queue Lifecycle

For thread-backed `todo/` items, GitHub replies are part of the default ledger.
For stacked review fixes, queue replies after local audit, then post them only
after the new top-of-stack PR exists. Keep every reply accurate about visibility:
fixed replies must name the PR where the fix is visible.

Before committing a follow-up fix, audit the worktree and staged changes:

```bash
git status --short
git diff -- <changed-files>
git diff --cached -- <changed-files>
# run focused checks
```

After committing and creating the follow-up PR, audit the reviewable range and
PR-visible diff:

```bash
git show --stat --oneline HEAD
git diff --stat "$fix_base"...HEAD
git diff "$fix_base"...HEAD -- <changed-files>
gh pr diff <fix-pr> --name-only
gh pr diff <fix-pr> --patch
```

If the fix PR does not exist yet, skip the `gh pr diff` commands and keep fixed
drafts queued without a URL. Post fixed replies only after the fix is visible in
the follow-up PR and a scoped dry run succeeds. Use the audit output to verify
the queued reply is true and to summarize changed files and checks in the final
handoff. Do not `git add` unless preparing the follow-up PR.

Create fixed drafts with:

```bash
python3 "$SKILL_DIR/scripts/review_reply_queue.py" add-fixed <review-item-file> \
  --summary '<summary>'
```

If the fix PR already exists, include it immediately:

```bash
python3 "$SKILL_DIR/scripts/review_reply_queue.py" add-fixed <review-item-file> \
  --summary '<summary>' \
  --fix-pr-url https://github.com/<owner>/<repo>/pull/<fix-pr>
```

Create declined drafts with:

```bash
python3 "$SKILL_DIR/scripts/review_reply_queue.py" add-declined <review-item-file> \
  --reason '<reason>'
```

After creating the new top-of-stack PR, attach its URL and post:

```bash
python3 "$SKILL_DIR/scripts/review_reply_queue.py" post-pending \
  --source-pr <reviewed-pr-number> \
  --fix-pr-url https://github.com/<owner>/<repo>/pull/<fix-pr> \
  --dry-run

python3 "$SKILL_DIR/scripts/review_reply_queue.py" post-pending \
  --source-pr <reviewed-pr-number> \
  --fix-pr-url https://github.com/<owner>/<repo>/pull/<fix-pr>
```

Useful queue commands:

- `list [--status pending|posting|failed|move_pending|move_failed|posted] [--source-pr <number>] [--bundle <path>] [--draft-id <id>] [--json]`
- `show <draft-id>`
- `preview <draft-id> [--fix-pr-url <url>]`
- `set-fix-pr <draft-id> <fix-pr-url>`
- `set-fix-pr --all-pending-fixed <fix-pr-url> --source-pr <number>`
- `post <draft-id> [--dry-run]`
- `post-pending [--source-pr <number>|--bundle <path>|--draft-id <id>] [--fix-pr-url <fix-pr-url>] [--dry-run]`
- `recover-posting <draft-id> --posted-reply-url <url> [--dry-run]`
- `recover-posting <draft-id> --no-reply-posted [--dry-run]`

Queue records live under `.github-review-workflow/reply-queue/`, one JSON file per
draft. They use stable GitHub identity fields; file paths are only locators.
The queue refuses duplicate active drafts for the same thread and disposition.

Reply templates:

- accepted in follow-up PR: `Addressed in <pr-url>: <summary>`
- declined or obsolete: `Not taking this change: <reason>`

The queue state is the recovery record:

- `pending`: draft exists but has not posted
- `posting`: mutation started; if left here without a reply URL, inspect GitHub,
  then use `recover-posting` with either the verified reply URL or
  `--no-reply-posted` before retrying
- `failed`: posting failed before a reply URL was recorded; item remains unmoved
- `move_pending` or `move_failed`: reply URL was recorded; rerun `post` to move
  the item without reposting
- `posted`: reply posted and local item moved

Use the direct follow-up script only as a single-item escape hatch, mostly for
non-stacked local-first work:

```bash
python3 "$SKILL_DIR/scripts/post_github_review_followup.py" <review-item-file> \
  --reply '<accurate reply>'
```

With the direct follow-up script, add `--resolve` only when the user explicitly
requested thread resolution and the fix or final disposition is visible on
GitHub in the intended branch or PR.

## Final Handoff

End with a compact local handoff:

- accepted fixes implemented
- ignored items and reasons
- files changed
- tests or checks run and results
- review bundle files moved
- GitHub replies posted, skipped, or failed
- whether any thread resolution, commit, push, PR, or branch update was avoided
  or explicitly performed
- current branch, follow-up PR URL if created, and any remaining queued drafts

Do not resolve threads unless the user explicitly asks for that follow-up.
