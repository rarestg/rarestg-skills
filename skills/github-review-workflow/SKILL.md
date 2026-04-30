---
name: github-review-workflow
description: >-
  Export a PR's clean inline review comments and CodeRabbit nitpicks into
  local files, then triage and address review feedback through an
  orchestrator-led local workflow. Use when given a GitHub pull request URL and
  asked to work through review comments without relying on noisy raw API blobs.
disable-model-invocation: true
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent
argument-hint: "<pr-url>"
user-invocable: true
---

# GitHub Review Workflow

Export inline PR review threads into a local queue, export CodeRabbit nitpicks
into a separate lower-priority queue, then follow this skill's local-first
orchestration workflow in `references/SOP.md`.

## Prerequisites

- `gh` installed and authenticated
- `python3` available in the shell
- the current working directory is the project that owns the PR

## Export

Set `SKILL_DIR` to this skill's installed or repo-local path, then run:

```bash
python3 "$SKILL_DIR/scripts/export_github_review_comments.py" <pr-url>
```

Useful export flags:

- `--include-resolved` to reprocess already-resolved threads
- `--include-ai-prompts` to preserve embedded AI-agent prompt sections; they
  are stripped by default

Read the full bundle before editing:

- `$SKILL_DIR/references/SOP.md`
- `GitHub Reviews/pr-<number>-<slug>/README.md`
- `GitHub Reviews/pr-<number>-<slug>/context/01-coderabbit-walkthrough.md` if it exists
- all files in `GitHub Reviews/pr-<number>-<slug>/todo/`
- all files in `GitHub Reviews/pr-<number>-<slug>/nitpicks/` if it exists;
  triage them as lower-priority local-only items unless the user asked to
  handle them now

## Defaults

- Keep code changes local by default: do not commit, push, create PRs, resolve
  GitHub threads, update the reviewed PR branch, or switch branches unless
  explicitly requested or confirmed.
- Review-thread replies are the one default GitHub mutation.
- For thread-backed `todo/` items, post the GitHub reply after local audit and
  before moving the item to `done/` or `ignored/`; if the fix is unpushed, say so
  in the reply.
- Triage up front: judge merit, group related items, detect conflicts or
  ordering, and decide what is worth delegating.
- Do a lightweight stack/base check before editing; deepen it only when the
  current branch, PR head, or intended fix branch is ambiguous.
- The orchestrator owns the queue. Implement small, obvious fixes directly.
- Delegate only bounded work units that justify worker overhead. A work unit
  may be one item or a small related group, never the whole queue.
- Audit locally and capture the relevant changed files/checks before posting a
  reply or moving files to `done/` or `ignored/`.
- Nitpicks are local-only by default because they are not review threads; do
  not use the follow-up script for them.
- Leave accepted fixes in the current working tree and report back unless the
  user explicitly requests commit, push, PR, or thread-resolution follow-through.
