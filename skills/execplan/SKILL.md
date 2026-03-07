---
name: execplan
description: >-
  Write a self-contained execution plan (ExecPlan) for complex, multi-step
  tasks. Use when asked to plan a large feature, significant refactor,
  multi-hour implementation, or when the user says "write a plan", "create an
  execplan", "plan this out", "design before building", or needs a structured
  approach before starting complex work.
allowed-tools: Bash, Read, Glob, Grep, Write, Edit
argument-hint: "[task description or path to existing plan]"
---

# ExecPlan

An ExecPlan is a self-contained, living design document that guides a stateless
agent (or novice human) through a complex implementation end-to-end. It replaces
vague task descriptions with concrete, verifiable steps. The bar: a fresh agent
with zero prior context reads the plan top-to-bottom and produces a working,
observable result.

## When to use

Use an ExecPlan when work spans multiple files, requires research, has
significant unknowns, or would take more than a focused session to complete.
For small, well-understood changes, skip the plan and just do the work.

## File organization

One plan per file. Store all plans in a `plans/` directory at the repo root.
Name files descriptively: `plans/add-webhook-support.md`,
`plans/migrate-to-v2-api.md`.

Multiple plans can exist in parallel. Each is independent and self-contained.
An agent can work on several plans concurrently — pick one up, advance it,
switch to another. If one plan depends on another, reference it by path
rather than duplicating its content.

Completed plans stay checked in. They serve as reference for future work and
provide context for how the codebase reached its current state.

## Workflow

### 1. Research first

Read relevant code, docs, configs, tests, and CI before writing anything.
Understand the current state well enough to explain it to someone who knows
nothing about the repo.

### 2. Write the plan

Follow the skeleton below. Start from it and flesh out sections as you
research. Every section exists for a reason.

### 3. Review before executing

Present the plan for user review. Do not start implementing until the plan
is approved.

### 4. Execute from the plan

Work through milestones sequentially. At every stopping point:
- Update Progress with what was done and what remains
- Record surprises and decisions in their sections
- Commit the updated plan alongside code changes

### 5. Keep it alive

The plan is a living document. When you discover something, change course, or
finish a milestone, update the plan immediately. A stale plan is dangerous.

## Core principles

- **Self-contained**: Include all needed context. A fresh agent with only the
  plan file must be able to succeed. Do not point to external docs without
  embedding the relevant content. Repeat assumptions you rely on.
- **Outcome-focused**: State what someone can do after the change that they
  couldn't before, and how to verify it.
- **Novice-guiding**: Name files by full repo-relative path, define jargon on
  first use, show exact commands with working directory and expected output.
- **Verifiable**: Every milestone has observable acceptance criteria. Phrase as
  behavior ("GET /health returns 200 OK"), not internals ("added HealthCheck
  struct").
- **Idempotent**: Steps should be safe to re-run. If a step is risky, describe
  recovery.

## Skeleton

Use the following structure. Omit sections only if genuinely irrelevant.

    # <Short, action-oriented title>

    Living document. Progress, Surprises & Discoveries, Decision Log, and
    Outcomes must be kept current as work proceeds.

    ## Purpose

    What someone gains after this change and how they can see it working.
    A few sentences, user-perspective.

    ## Progress

    - [x] (2025-10-01 13:00Z) Completed step
    - [ ] Incomplete step
    - [ ] Partially done (completed: X; remaining: Y)

    Update at every stopping point. Use timestamps to track pace.

    ## Context and Orientation

    Current state as if the reader knows nothing. Key files and modules by
    full path. Define non-obvious terms. Do not reference prior plans unless
    they are checked into the repo.

    ## Plan of Work

    Sequence of edits in prose. For each: file path, location (function or
    module), and what changes. Concrete and minimal.

    ## Milestones

    Break work into independently verifiable chunks. For each milestone:
    scope, what exists at the end that didn't before, commands to run,
    expected results.

    When unknowns are significant, include prototyping milestones that
    validate feasibility before committing to a full implementation.
    Label these clearly and state criteria for promoting or discarding.

    ## Validation and Acceptance

    How to exercise the system and what to observe. Exact test commands
    and expected results. Show inputs and outputs so a novice can tell
    success from failure.

    ## Surprises & Discoveries

    Unexpected behaviors, bugs, performance tradeoffs, or insights found
    during implementation. Include concise evidence (test output is ideal).

    ## Decision Log

    - Decision: ...
      Rationale: ...
      Date: ...

    ## Outcomes & Retrospective

    What was achieved, what remains, lessons learned. Written at major
    milestones and at completion.

## Guardrails

- Do not start implementing before the plan is written and reviewed.
- Do not leave Progress stale — update it at every stopping point.
- Do not describe changes abstractly. Describe observable behavior.
- Do not reference external docs without embedding the relevant content.
- Do not over-specify implementation details at the expense of clarity about
  intent and outcomes. Explain the why, be concrete about the what, leave
  incidental how to the implementer.
