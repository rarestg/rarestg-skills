---
name: github-review-workflow
description: >-
  Export a PR's clean inline review comments into local files, then triage
  and address them sequentially with focused agents. Use when given a GitHub
  pull request URL and asked to work through review comments without relying
  on noisy raw API blobs.
disable-model-invocation: true
allowed-tools: Bash, Read, Write, Edit, Glob, Grep, Agent
argument-hint: "<pr-url>"
user-invocable: true
---

# GitHub Review Workflow

Export inline PR review threads into a local queue, then follow this skill's
`references/SOP.md`.

## Prerequisites

- `gh` installed and authenticated
- `python3` available in the shell
- the current working directory is the project that owns the PR

## Script Path

Run bundled scripts from this skill directory, not from the project root.
Set `SKILL_DIR` to the installed or repo-local path for this skill.

Examples:

```bash
python3 "$SKILL_DIR/scripts/export_github_review_comments.py" <pr-url>
python3 "$SKILL_DIR/scripts/post_github_review_followup.py" <review-item-file> ...
```

## Export

Run:

```bash
python3 "$SKILL_DIR/scripts/export_github_review_comments.py" <pr-url>
```

Useful export flags:

- `--include-resolved` to reprocess already-resolved threads
- `--strip-ai-prompts` to remove embedded AI-agent prompt sections

Then open:

- `$SKILL_DIR/references/SOP.md`
- `GitHub Reviews/pr-<number>-<slug>/README.md`
- `GitHub Reviews/pr-<number>-<slug>/context/00-dispatch-guidance.md`
- `GitHub Reviews/pr-<number>-<slug>/context/01-coderabbit-walkthrough.md` if it exists

## Non-Negotiables

- Work `todo/` sequentially
- Before editing, check whether this PR has open children in the current stack;
  if so, put accepted fixes on the current top-of-stack branch
- Do a local merit pass before changing code
- For accepted items, delegate to a fresh sub-task/subagent with no prior
  conversation context where the runtime supports that
- Give the worker only `context/00-dispatch-guidance.md`,
  `context/01-coderabbit-walkthrough.md` if present, and the assigned item
- Do not mention the rest of the queue in the worker prompt
- Audit locally before moving files to `done/` or `ignored/`
- Use the bundled follow-up script only after local audit
