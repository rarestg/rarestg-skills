# GitHub Review SOP

## Purpose

Turn a GitHub PR URL into a clean local queue of review threads and a separate
CodeRabbit nitpick queue, then triage the full bundle up front, address
accepted work locally, and post accurate review-thread replies as the GitHub
ledger of what was handled.

This reference lives inside the skill. The bundled scripts generate review
bundles under `GitHub Reviews/` in the current project.

The workflow exists to avoid these failure modes:

- treating summary reviews as the action queue
- blindly implementing every bot suggestion
- pushing partial fixes that repeatedly retrigger review automation

## Source Of Truth

When exporting review data:

- use `pullRequest.reviewThreads[].comments[]` as the actionable queue
- use `pullRequest.comments[]` only for optional top-level context such as a
  CodeRabbit walkthrough
- treat `pullRequest.reviews[]` as summary metadata, except structured
  CodeRabbit nitpick sections exported separately to `nitpicks/`
- prefer `bodyText` by default
- use raw `body` when structural Markdown matters and `bodyText` flattens away
  important boundaries; currently this is needed for CodeRabbit walkthrough
  and nitpick detail blocks

Review-summary wrappers such as `Actionable comments posted: 2` are not actionable items.
CodeRabbit nitpick details may contain concrete file/line suggestions, but they
remain lower-priority than inline review threads.

## Bundle Layout

Each PR exports to `GitHub Reviews/pr-<number>-<slug>/`.

Expected files:

- `README.md`: local index for the bundle
- `manifest.json`: machine-readable export metadata
- `context/00-dispatch-guidance.md`: short context brief
- `context/01-coderabbit-walkthrough.md`: optional top-level context
- `todo/`: review items not yet handled
- `nitpicks/`: CodeRabbit nitpick summary items, lower priority than `todo/`
- `done/`: accepted, implemented locally, and audited; for review-thread
  items, the GitHub reply has also been posted
- `ignored/`: not taken locally after merit, scope, or audit review, with a
  GitHub reply posted when the item has a review thread

Each review item file represents one review thread. It includes the IDs needed
for optional GitHub follow-through:

- `PR URL`
- `Thread ID`
- `Primary Comment Database ID` when GitHub provides it
- `Discussion URL`

Do not delete review files. The folder path is the status record. Create
status folders as needed.

Nitpick files come from CodeRabbit review-summary details, not GitHub review
threads. They include a `Review URL`, but not a `Thread ID`, and the bundled
follow-up script is not used for them.

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
- `--out-root <path>` writes bundles somewhere other than `GitHub Reviews/`

The bundled exporter auto-creates `GitHub Reviews/` and seeds
`GitHub Reviews/.gitignore` when needed.

Re-running the exporter is safe. It preserves existing recognized status
placement for inline threads by `Thread ID`, and for nitpicks by `Review ID`,
file, line range, and title. Newly discovered inline threads land in `todo/`;
newly discovered nitpicks land in `nitpicks/`.
The exporter does not delete existing local review files. If the current export
filter excludes a thread, for example because it is already resolved and
`--include-resolved` was not used, its previous local status file may still
remain on disk even though it is absent from the new README and manifest.

After export, open:

- `$SKILL_DIR/references/SOP.md`
- `GitHub Reviews/pr-<number>-<slug>/README.md`
- `GitHub Reviews/pr-<number>-<slug>/manifest.json`
- `GitHub Reviews/pr-<number>-<slug>/context/00-dispatch-guidance.md`
- `GitHub Reviews/pr-<number>-<slug>/context/01-coderabbit-walkthrough.md` if it exists
- all files in `GitHub Reviews/pr-<number>-<slug>/todo/`
- all files in `GitHub Reviews/pr-<number>-<slug>/nitpicks/` if it exists;
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

## Stack Safety

Before editing, do a lightweight stack/base check. Use it to choose or confirm
the local base for fixes, not to update remote branches by default. Deepen the
check only when the current branch, PR head, or intended fix branch is
ambiguous.

Useful example commands:

```bash
gh pr view <number-or-url> --json number,headRefName,baseRefName,title
gh pr list --state open --json number,headRefName,baseRefName,title
```

If the PR may be stacked, walk from the reviewed PR's head branch:

- Find open PRs where `baseRefName == <current-head>`.
- If exactly one child exists, set `<current-head>` to that child's
  `headRefName` and continue.
- If no child exists, `<current-head>` is the current top-of-stack head.
- If multiple children exist or the chain is otherwise ambiguous, stop and ask
  the user which branch should receive the fix.

If the final top-of-stack head differs from the reviewed PR's head, the
reviewed PR is not top-of-stack.

Default behavior keeps code changes local:

- do not commit, push, create PRs, resolve GitHub threads, or update the
  reviewed PR branch unless explicitly requested
- do not create a branch unless explicitly requested
- if the current branch is not the intended local base, ask before switching
  branches
- if the reviewed PR is lower in the stack, report the likely top-of-stack base
  and ask before switching unless the user already made the target branch clear
- if the correct local base is ambiguous, stop and ask the user which branch or
  worktree should receive the fix

This avoids silently changing a lower PR branch or starting a remote
cat-and-mouse review loop. The final handoff should report the current branch
and the likely stacked-PR base if the user later wants one.

## Review Loop

Handle `todo/` before `nitpicks/` unless the user explicitly asks otherwise.
Use the initial triage to choose bounded work units: one review item, or a
small group of related items that share one implementation fix.

For each work unit:

1. Inspect the referenced code directly.
2. Reassess merit before changing code.
3. Implement small, obvious fixes directly.
4. Delegate only if the work unit is large, complex, multi-file, risky, or
   benefits from isolated investigation.
5. If delegating, give the worker only the bounded work unit, relevant context
   files, and relevant item files. Do not hand over the full queue.
6. Audit the final diff yourself, including worker output.
7. Capture lightweight local evidence before posting: relevant changed files,
   verification run, `git status --short`, and enough `git diff -- <files>`
   review to know the reply is true. Do not stage changes by default.
8. For each thread-backed item in the work unit, post the GitHub reply before
   moving the file:
   - accepted: `Addressed locally but not pushed: <summary>`
   - ignored: `Not taking this change: <reason>`
9. Move local item files only after the required reply succeeds:
   - `done/` for accepted fixes implemented locally, audited, and replied to
   - `ignored/` for items not taken locally after merit, scope, or audit review,
     with the reason replied to on GitHub

Do not resolve GitHub threads as part of the default loop. Leave accepted fixes
in the current working tree and report back. If reply posting fails, leave the
item in `todo/`, report the blocker, and do not mark it `done/` or `ignored/`
unless the user explicitly chooses to skip the GitHub reply.

## Nitpick Loop

Read and triage `nitpicks/` during the initial bundle pass. Execute them only
after `todo/` is empty or when the user explicitly asks to handle nitpicks.
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

## Delegation Granularity

The orchestrator owns the queue. Workers are optional and should be used only
when the overhead is justified.

Delegate when:

- a fix touches several files or subsystems
- the correct approach requires nontrivial investigation
- tests need meaningful design or repair
- several comments point to one shared implementation issue
- the change is risky enough to benefit from isolated implementation

Do not delegate:

- typo, docs, naming, or comment-only fixes
- one-line correctness fixes the orchestrator can safely make
- simple test expectation updates
- purely mechanical edits
- ignored or obviously low-merit suggestions

A delegated work unit should be small enough to review completely, but large
enough to avoid duplicated setup cost. Prefer one related group over several
nearly identical workers. Never hand the whole queue to one worker.

When delegating, give the worker only the context needed for that bounded work
unit:

- `context/00-dispatch-guidance.md`
- `context/01-coderabbit-walkthrough.md` if relevant
- the assigned review item files
- specific implementation constraints discovered during triage

Workers must reassess merit, make the smallest defensible fix if valid, avoid
unrelated files, and leave final status-folder movement to the orchestrator.

## GitHub Replies And Follow-Through

For thread-backed `todo/` items, GitHub replies are part of the default ledger.
Post the reply after local audit and before moving the item file. Keep every
reply accurate about visibility: if the fix only exists in the working tree,
say that it was addressed locally but not pushed.
Review-thread replies are the one default GitHub mutation; commits, pushes, PR
creation, branch updates, and thread resolution remain opt-in.

Before posting a reply, capture lightweight local evidence:

```bash
git status --short
git diff -- <changed-files>
```

Use this evidence to verify the reply is true and to summarize changed files
and checks in the final handoff. Do not `git add` by default; staging can
interfere with the user's commit plan.

Do not resolve review threads while fixes exist only in the working tree unless
the user explicitly requests resolution.

For accepted items fixed locally but not pushed:

```bash
python3 "$SKILL_DIR/scripts/post_github_review_followup.py" <review-item-file> \
  --reply 'Addressed locally but not pushed: <summary>'
```

For accepted items available in a follow-up PR that the user explicitly asked
you to create:

```bash
python3 "$SKILL_DIR/scripts/post_github_review_followup.py" <review-item-file> \
  --reply 'Addressed in <stacked-fix-pr-url>: <summary>'
```

For ignored items:

```bash
python3 "$SKILL_DIR/scripts/post_github_review_followup.py" <review-item-file> \
  --reply 'Not taking this change: <reason>'
```

Add `--resolve` only when the user explicitly requested thread resolution and
the fix or final disposition is visible on GitHub in the intended branch or PR.

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
- current branch and suggested stacked-PR base if follow-up PR creation is
  desired

Do not create the stacked branch, create a PR, push, or resolve threads unless
the user explicitly asks for that follow-up.

## Practical Notes

- CodeRabbit usually places walkthrough context in `comments`, summary metadata
  in `reviews`, and actionable inline comments in `reviewThreads`
- Cursor and Codex generally follow the same pattern
- The generated dispatch guidance is task context, not a second source of
  policy; this SOP is the canonical procedure
