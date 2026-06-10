---
name: agents-md
description: >-
  Create, rewrite, or maintain a repository's AGENTS.md as a short dispatcher
  for coding agents. Use when asked to write an AGENTS.md from scratch, update
  stale agent instructions, shrink a bloated AGENTS.md, add repo guidance for
  AI/coding agents, or document where agents should find source-of-truth docs,
  invariants, validation commands, and workflow rules. Triggers on: "create
  AGENTS.md", "write an agents file", "update AGENTS.md", "maintain
  AGENTS.md", "fix our agent instructions", "make this repo easier for
  Codex/Claude/agents", "rewrite this bloated AGENTS.md".
allowed-tools: Bash, Read, Glob, Grep, Write, Edit
argument-hint: '[create | update | shrink]'
---

# AGENTS.md

`AGENTS.md` is a map, not a manual. Its job is to orient the agent, route it
to the real sources of truth, call out non-negotiable constraints, and explain
how to verify work. It should not try to be the truth itself.

## Workflow

### 1. Inspect the repo, then write

Read top-level docs and structure first: `README*`, existing `AGENTS.md`, docs
directories, manifests, CI workflows, test/lint configs, and any active
plan/spec/design-doc folders.

### 2. Include only what passes this rubric

Before adding any line, ask:

1. Will this matter for many tasks, not just one area?
2. Will it still be true in a month or two?
3. Would the agent not reliably infer it from code or tests?
4. Does it help the agent act, not just know?
5. Is there a deeper source of truth or enforcement behind it?

If several answers are "no", put it in a deeper repo doc or encode it in
tooling — not in `AGENTS.md`.

### 3. Use this structure

- Repo purpose
- Repo map
- Sources of truth (link to `ARCHITECTURE.md`, design docs, specs, plans,
  generated references, quality/security docs)
- Non-negotiable invariants
- Validation / definition of done
- Navigation to deeper context

For larger repos, link outward instead of embedding detail. Route to subsystem
or nested agent docs rather than duplicating them. For tiny repos, a single
concise file may be enough.

### 4. Validate with the freshness test

A finished `AGENTS.md` should let a fresh agent quickly answer:

- What am I looking at?
- Where do I go for deeper context?
- What must I not break?
- How do I check my work?

If any answer is missing, the file is incomplete.

### 5. When updating an existing AGENTS.md

Reduce by default, do not expand. Delete obsolete guidance aggressively.
Replace duplicated detail with links to canonical docs.

### 6. Keep it from going stale

- One canonical home per topic — link from `AGENTS.md`, don't duplicate
- Prefer generated docs for facts derivable from code
- Promote repeated review comments into lints, tests, scripts, or CI
- Update the map when sources of truth move, not when local details change
- If a new rule matters, either add a canonical doc or encode it in tooling

## Guardrails

- Do not turn `AGENTS.md` into the full knowledge base unless the repo is tiny.
- Do not embed full product specs, detailed subsystem behavior, large
  architectural explanations, or long endpoint/file inventories that change often.
- Do not duplicate content that already lives in another repo doc — link to it.
- Do not include style opinions unless they are enforced somewhere real.
- Do not preserve stale sections just because they already exist.
