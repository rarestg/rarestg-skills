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

Turn a GitHub PR URL into a clean local queue of inline review threads, then work that queue one item at a time.

`references/SOP.md` is the canonical procedure. This file is only the entrypoint.

## Prerequisites

- `gh` installed and authenticated
- `python3` available in the shell
- the current working directory is the project that owns the PR

## Helper Scripts

Use the bundled scripts in this skill's `scripts/` directory:

- [export_github_review_comments.py](scripts/export_github_review_comments.py) exports the PR bundle into `GitHub Reviews/`
- [post_github_review_followup.py](scripts/post_github_review_followup.py) posts a reply and/or resolves a thread after local audit

## Export

Run:

```bash
python3 scripts/export_github_review_comments.py <pr-url>
```

Optional: add `--strip-ai-prompts` if you want the exported review item bodies to drop embedded `Prompt for AI Agents` sections.

Then open:

- `references/SOP.md`
- `GitHub Reviews/pr-<number>-<slug>/README.md`
- `GitHub Reviews/pr-<number>-<slug>/context/00-dispatch-guidance.md`
- `GitHub Reviews/pr-<number>-<slug>/context/01-coderabbit-walkthrough.md` if it exists

## Non-Negotiables

- Work `todo/` sequentially
- Do a local merit pass before changing code
- For accepted items, delegate to a fresh sub-task with no prior conversation context (`fork_context: false` where applicable), and give it only `context/00-dispatch-guidance.md`, `context/01-coderabbit-walkthrough.md` if present, and the assigned review item file
- Do not mention the rest of the queue in the worker prompt
- Audit locally before moving files to `done/` or `ignored/`
- Use `python3 scripts/post_github_review_followup.py <review-item-file> ...` only after local audit
