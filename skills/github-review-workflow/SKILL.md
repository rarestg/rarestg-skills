---
name: github-review-workflow
description: >-
  Export a PR's clean inline review comments, CodeRabbit outside-diff comments,
  and CodeRabbit nitpicks into local files, then triage review feedback through
  a stack-aware orchestrator workflow with durable reply drafts for follow-up
  PRs. Use when given a GitHub pull request URL and asked to work through review
  comments without relying on noisy raw API blobs.
disable-model-invocation: true
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent
argument-hint: "<pr-url>"
user-invocable: true
---

# GitHub Review Workflow

Export inline PR review threads into a local queue, export CodeRabbit
outside-diff comments and nitpicks into separate local-only queues, then follow
this skill's stack-aware orchestration workflow in `references/SOP.md`.

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
- `.github-review-workflow/pr-<number>-<slug>/README.md`
- `.github-review-workflow/pr-<number>-<slug>/context/01-coderabbit-walkthrough.md` if it exists
- all files in `.github-review-workflow/pr-<number>-<slug>/todo/`
- all files in `.github-review-workflow/pr-<number>-<slug>/outside-diff/` if it exists;
  triage them as local-only review-summary items because GitHub could not post
  them inline
- all files in `.github-review-workflow/pr-<number>-<slug>/nitpicks/` if it exists;
  triage them as lower-priority local-only items unless the user asked to
  handle them now

## Defaults

- For stacked PR review-comment cleanup, accepted fixes land in a new PR stacked
  above the current top PR. Do not amend, rebase, force-push, or otherwise update
  older reviewed PR branches for these fixes.
- If the reviewed PR is not part of a stack and the user did not ask for PR
  follow-through, keep code changes local and use the direct follow-up script.
- Fixed stacked-review replies are queued locally until the follow-up PR exists,
  then posted as `Addressed in <fix-pr-url>: <summary>`.
- Declined or obsolete thread-backed comments use the same durable queue and may
  be posted immediately as `Not taking this change: <reason>`.
- Triage up front: judge merit, group related items, detect conflicts or
  ordering, and decide what is worth delegating.
- Do a lightweight stack/base check before editing; deepen it only when the
  current branch, PR head, stack top, or intended fix branch is ambiguous.
- The orchestrator owns the queue. Implement small, obvious fixes directly.
- Delegate only bounded work units that justify worker overhead. A work unit
  may be one item or a small related group, never the whole queue.
- Audit locally and capture the relevant changed files/checks before queueing or
  posting a reply.
- Outside-diff comments and nitpicks are local-only by default because they are
  not review threads; do not use the queue or follow-up script for them.

## Reply Queue

Queue accepted stacked-review fixes before the follow-up PR exists:

```bash
python3 "$SKILL_DIR/scripts/review_reply_queue.py" add-fixed <review-item-file> \
  --summary '<summary>'
```

After creating the new top-of-stack PR, attach the PR URL and post pending
replies:

```bash
python3 "$SKILL_DIR/scripts/review_reply_queue.py" post-pending \
  --source-pr <reviewed-pr-number> \
  --fix-pr-url https://github.com/<owner>/<repo>/pull/<fix-pr> \
  --dry-run

python3 "$SKILL_DIR/scripts/review_reply_queue.py" post-pending \
  --source-pr <reviewed-pr-number> \
  --fix-pr-url https://github.com/<owner>/<repo>/pull/<fix-pr>
```

Declined comments can use the same queue:

```bash
python3 "$SKILL_DIR/scripts/review_reply_queue.py" add-declined <review-item-file> \
  --reason '<reason>'
python3 "$SKILL_DIR/scripts/review_reply_queue.py" post-pending \
  --source-pr <reviewed-pr-number> \
  --dry-run
python3 "$SKILL_DIR/scripts/review_reply_queue.py" post-pending \
  --source-pr <reviewed-pr-number>
```

Use `post_github_review_followup.py` only as a direct single-item escape hatch.
