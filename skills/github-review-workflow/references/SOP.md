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

## Queues

Inline review threads are the main action queue. CodeRabbit nitpicks are
exported separately, triaged up front, and lower priority by default. Summary
review wrappers are context, not work items.

## Bundle Layout

Each PR exports to `GitHub Reviews/pr-<number>-<slug>/`.

Expected files:

- `README.md`: local index for the bundle
- `manifest.json`: machine-readable export metadata
- `context/00-dispatch-guidance.md`: short context brief
- `context/01-coderabbit-walkthrough.md`: optional top-level context
- `todo/`: review items not yet handled
- `nitpicks/`: CodeRabbit nitpick summary items, lower priority than `todo/`
- `done/`: accepted, locally implemented, audited, and replied to when
  thread-backed
- `ignored/`: declined after merit, scope, or audit review, and replied to when
  thread-backed

Review item files include the IDs needed for follow-up replies. Nitpick files
are not GitHub review threads and must not use the bundled follow-up script. Do
not delete review files; folder placement is the status record.

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

Re-running the exporter preserves recognized local status placement and adds
newly discovered inline threads to `todo/` and nitpicks to `nitpicks/`.

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

If the PR appears stacked, identify the likely top-of-stack base and report it
in the final handoff.

## Review Loop

Handle `todo/` before `nitpicks/` unless the user explicitly asks otherwise.
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

Post with:

```bash
python3 "$SKILL_DIR/scripts/post_github_review_followup.py" <review-item-file> \
  --reply '<accurate reply>'
```

Reply templates:

- accepted locally: `Addressed locally but not pushed: <summary>`
- accepted in an explicitly requested follow-up PR: `Addressed in <pr-url>: <summary>`
- ignored: `Not taking this change: <reason>`

Add `--resolve` only when the user explicitly requested thread resolution and
the fix or final disposition is visible on GitHub in the intended branch or PR.

Useful flags:

- `--dry-run` to show the target commands without mutating GitHub
- `--show-metadata` to inspect the parsed IDs
- `--reply-file -` to read a multi-line reply from stdin

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
