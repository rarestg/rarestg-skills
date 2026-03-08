# GitHub Review SOP

## Purpose

Turn a GitHub PR URL into a clean local queue of review threads, then work that queue one item at a time with a strong bias toward small, justified fixes.

This reference lives inside the skill. The bundled scripts still generate review bundles under `GitHub Reviews/` in the current project.

The workflow exists to avoid two failure modes:

- treating summary reviews as the action queue
- blindly implementing every bot suggestion

## Source Of Truth

When exporting review data:

- use `pullRequest.reviewThreads[].comments[]` as the actionable queue
- use `pullRequest.comments[]` only for optional top-level context such as a CodeRabbit walkthrough
- treat `pullRequest.reviews[]` as summary metadata, not as action items
- prefer `bodyText` by default
- use raw `body` when structural Markdown matters and `bodyText` flattens away important boundaries; currently this is needed for CodeRabbit detail blocks

Review-summary wrappers such as `Actionable comments posted: 2` are not actionable items.

## Bundle Layout

Each PR exports to `GitHub Reviews/pr-<number>-<slug>/`.

Expected files:

- `README.md`: local index for the bundle
- `manifest.json`: machine-readable export metadata
- `context/00-dispatch-guidance.md`: short worker brief
- `context/01-coderabbit-walkthrough.md`: optional top-level context
- `todo/`: review items not yet handled
- `done/`: accepted and handled review items
- `ignored/`: rejected review items

Each review item file represents one review thread. It includes the IDs needed for GitHub follow-through:

- `PR URL`
- `Thread ID`
- `Primary Comment Database ID` when GitHub provides it
- `Discussion URL`

Do not delete review files. The folder path is the status record.

## Export

```bash
python3 scripts/export_github_review_comments.py https://github.com/<owner>/<repo>/pull/<number>
```

Optional: add `--strip-ai-prompts` if you want exported review item bodies to omit embedded `Prompt for AI Agents` sections while keeping the rest of the thread.

The bundled exporter auto-creates `GitHub Reviews/` and seeds `GitHub Reviews/.gitignore` when needed.

After export, open:

- `references/SOP.md`
- `GitHub Reviews/pr-<number>-<slug>/README.md`
- `GitHub Reviews/pr-<number>-<slug>/context/00-dispatch-guidance.md`
- `GitHub Reviews/pr-<number>-<slug>/context/01-coderabbit-walkthrough.md` if it exists

## Review Loop

Work `todo/` sequentially.

For each review item:

1. Read the review item, the dispatch guidance, and the walkthrough file if present.
2. Inspect the referenced code directly.
3. Decide whether the comment has enough merit to justify code changes.
4. If not, move the file to `ignored/`.
5. If yes, dispatch exactly one worker for that item.
6. Spawn that worker with `fork_context: false` so it starts fresh with no prior conversation context.
7. Give the worker only:
   - `context/00-dispatch-guidance.md`
   - `context/01-coderabbit-walkthrough.md` if present
   - the assigned review item file
8. Do not mention the rest of the queue, item count, or unassigned review comments.
9. Wait for the worker result.
10. Audit the diff yourself.
11. If accepted, move the file to `done/`.
12. If rejected after audit, move the file to `ignored/`.

Never hand the whole queue to one worker.

## Merit Gate

Default posture: do not implement a comment unless it improves correctness, maintainability, accessibility, safety, or developer clarity with proportional complexity.

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

## Worker Guardrails

Every worker should operate under these constraints:

- fresh context only
- assigned review item only
- read only the supplied review docs plus the code needed to evaluate them
- reassess merit before editing
- implement the smallest defensible fix if valid
- make no code change if the comment is not worth taking
- do not address adjacent or related review items
- do not touch files outside the assigned ownership unless the parent explicitly expands scope

If two comments truly require one atomic fix, the parent agent must decide that before dispatch.

## GitHub Follow-Through

Only after local audit, use the helper script if you want to reply or resolve on GitHub:

```bash
python3 scripts/post_github_review_followup.py <review-item-file> \
  --reply 'Addressed locally: <summary>' \
  --resolve
```

Useful flags:

- `--dry-run` to show the target commands without mutating GitHub
- `--show-metadata` to inspect the parsed IDs
- `--reply-file -` to read a multi-line reply from stdin

Use `Discussion URL` for manual UI spot-checking when present. Use `Thread ID` for resolve calls. `Primary Comment Database ID` is only needed for REST replies and may be unavailable on some exported items.

## Practical Notes

- CodeRabbit usually places walkthrough context in `comments`, summary metadata in `reviews`, and actionable inline comments in `reviewThreads`
- Cursor and Codex generally follow the same pattern
- The generated worker brief is task context, not a second source of policy; this SOP is the canonical procedure
