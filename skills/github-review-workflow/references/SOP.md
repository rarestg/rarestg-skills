# GitHub Review SOP

## Purpose

Turn a GitHub PR URL into a clean local queue of review threads, then work
that queue one item at a time with a strong bias toward small, justified fixes.

This reference lives inside the skill. The bundled scripts generate review
bundles under `GitHub Reviews/` in the current project.

The workflow exists to avoid two failure modes:

- treating summary reviews as the action queue
- blindly implementing every bot suggestion

## Source Of Truth

When exporting review data:

- use `pullRequest.reviewThreads[].comments[]` as the actionable queue
- use `pullRequest.comments[]` only for optional top-level context such as a
  CodeRabbit walkthrough
- treat `pullRequest.reviews[]` as summary metadata, not as action items
- prefer `bodyText` by default
- use raw `body` when structural Markdown matters and `bodyText` flattens away
  important boundaries; currently this is needed for CodeRabbit detail blocks

Review-summary wrappers such as `Actionable comments posted: 2` are not actionable items.

## Bundle Layout

Each PR exports to `GitHub Reviews/pr-<number>-<slug>/`.

Expected files:

- `README.md`: local index for the bundle
- `manifest.json`: machine-readable export metadata
- `context/00-dispatch-guidance.md`: short worker brief
- `context/01-coderabbit-walkthrough.md`: optional top-level context
- `todo/`: review items not yet handled
- `done/`: accepted, implemented, audited, and followed up on GitHub
- `ignored/`: rejected after audit, with GitHub follow-up posted

Each review item file represents one review thread. It includes the IDs needed
for GitHub follow-through:

- `PR URL`
- `Thread ID`
- `Primary Comment Database ID` when GitHub provides it
- `Discussion URL`

Do not delete review files. The folder path is the status record.

## Export

Run scripts by their path inside this skill directory. Do not run
`python3 scripts/...` from the project root unless that happens to be the skill
directory. Set `SKILL_DIR` to this skill's installed or repo-local path.

```bash
python3 "$SKILL_DIR/scripts/export_github_review_comments.py" \
  https://github.com/<owner>/<repo>/pull/<number>
```

Useful flags:

- `--strip-ai-prompts` omits embedded `Prompt for AI Agents` sections
- `--include-resolved` includes already-resolved inline review threads
- `--out-root <path>` writes bundles somewhere other than `GitHub Reviews/`

The bundled exporter auto-creates `GitHub Reviews/` and seeds
`GitHub Reviews/.gitignore` when needed.

Re-running the exporter is safe. It preserves existing `todo/`, `done/`, and
`ignored/` placement by thread id; newly discovered threads land in `todo/`.

After export, open:

- `$SKILL_DIR/references/SOP.md`
- `GitHub Reviews/pr-<number>-<slug>/README.md`
- `GitHub Reviews/pr-<number>-<slug>/context/00-dispatch-guidance.md`
- `GitHub Reviews/pr-<number>-<slug>/context/01-coderabbit-walkthrough.md` if it exists

## Stack Safety

Before editing, determine whether the reviewed PR is the top of the current
stack.

1. Find this PR's head branch, for example:

   ```bash
   gh pr view <number-or-url> --json number,headRefName,baseRefName,title
   ```

2. Find open PR relationships:

   ```bash
   gh pr list --state open --json number,headRefName,baseRefName,title
   ```

3. Walk the stack from the reviewed PR's head branch:
   - Find open PRs where `baseRefName == <current-head>`.
   - If exactly one child exists, set `<current-head>` to that child's
     `headRefName` and continue.
   - If no child exists, `<current-head>` is the current top-of-stack head.
   - If multiple children exist or the chain is otherwise ambiguous, stop and
     ask the user which branch should receive the fix.

If the final top-of-stack head differs from the reviewed PR's head, the
reviewed PR is not top-of-stack.

If the reviewed PR is not top-of-stack:

- do not edit that lower PR branch
- check out or create a branch at the final top-of-stack head
- apply accepted fixes on top of the latest stacked code
- reply on the original review thread with a link to the top-stack fix PR
- do not resolve the lower PR's thread unless the user explicitly wants that

This avoids rebasing every PR above the reviewed branch for a small review fix.

## Review Loop

Work `todo/` sequentially.

For each review item:

1. Read the review item, dispatch guidance, and walkthrough if present.
2. Inspect the referenced code directly.
3. Decide whether the comment has enough merit to justify code changes.
4. If not, post a GitHub reply explaining why, then move the file to
   `ignored/`.
5. If yes, dispatch exactly one worker for that item.
6. Delegate to a fresh sub-task/subagent with no prior conversation context
   where the runtime supports that.
7. Give the worker only:
   - `context/00-dispatch-guidance.md`
   - `context/01-coderabbit-walkthrough.md` if present
   - the assigned review item file
8. Do not mention the rest of the queue, item count, or unassigned review comments.
9. Wait for the worker result.
10. Audit the diff yourself.
11. Post the required GitHub follow-up before moving the file:
    - If accepted on the reviewed PR branch: reply with the fix summary, resolve
      the thread, and move to `done/`.
    - If accepted on a top-stack branch because the reviewed PR is lower in the
      stack: reply with the fix summary and top-stack PR link, do not resolve
      unless the user explicitly requested it, and move to `done/`.
    - If rejected after audit: reply with the reason. Resolve only if no
      further discussion is needed. Move to `ignored/`.

Never hand the whole queue to one worker.

## Merit Gate

Default posture: do not implement a comment unless it improves correctness,
maintainability, accessibility, safety, or developer clarity with proportional
complexity.

Bias against:

- premature abstractions
- defensive code for hypothetical failures with no local evidence
- helpers or files that centralize logic still used in one place
- renames that add words but not clarity
- tests that only restate the implementation
- comments that mostly create stylistic churn

Bias toward:

- concrete bug fixes
- validation at trust boundaries
- fixes for already observed regressions
- low-complexity accessibility fixes
- documentation fixes that remove factual contradictions

When in doubt, prefer the simpler change or no change.

## Worker Boundary

Workers get one review item and only the context listed in the review loop.
They reassess merit, make the smallest defensible fix if valid, and avoid
adjacent review items or unrelated files. If two comments truly require one
atomic fix, the parent agent must decide that before dispatch.

## GitHub Follow-Through

Every review item must receive a GitHub follow-up reply after local audit. Do
not move files to `done/` or `ignored/` until follow-through is complete.

For accepted items fixed on the reviewed PR branch:

```bash
python3 "$SKILL_DIR/scripts/post_github_review_followup.py" <review-item-file> \
  --reply 'Addressed locally: <summary>' \
  --resolve
```

For accepted items fixed on a top-stack branch because the reviewed PR is lower
in the stack:

```bash
python3 "$SKILL_DIR/scripts/post_github_review_followup.py" <review-item-file> \
  --reply 'Addressed in <top-stack-fix-pr-url>: <summary>'
```

Do not add `--resolve` for lower-stack threads unless the user explicitly
requested it.

For rejected items:

```bash
python3 "$SKILL_DIR/scripts/post_github_review_followup.py" <review-item-file> \
  --reply 'Not taking this change: <reason>'
```

Resolve rejected threads only when no further discussion is needed.

Useful flags:

- `--dry-run` to show the target commands without mutating GitHub
- `--show-metadata` to inspect the parsed IDs
- `--reply-file -` to read a multi-line reply from stdin

If a reply succeeds but resolving fails, do not post a duplicate reply. Re-run
the follow-up script with `--resolve` only after fixing the underlying
GitHub/auth issue.

Use `Discussion URL` for manual UI spot-checking when present. Use `Thread ID`
for resolve calls. `Primary Comment Database ID` is only needed for REST
replies and may be unavailable on some exported items.

## Practical Notes

- CodeRabbit usually places walkthrough context in `comments`, summary metadata
  in `reviews`, and actionable inline comments in `reviewThreads`
- Cursor and Codex generally follow the same pattern
- The generated worker brief is task context, not a second source of policy;
  this SOP is the canonical procedure
