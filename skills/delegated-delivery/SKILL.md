---
name: delegated-delivery
description: >-
  Run a meaningful coding ticket through a delegated delivery workflow:
  tighten the ticket, assign one ticket owner, delegate implementation, get
  an independent review, triage findings, validate the result, and return a
  compact outcome packet. Use when the user wants structured agent execution
  with clear scope, ownership, and review rather than a single-pass
  implementation. Triggers on: "delegate this ticket", "use a sub-PM", "run
  this through worker and reviewer", "own this ticket end to end", "send
  this for independent review", or "close this out and report back". Skip
  trivial fixes and tasks that are still too vague to delegate.
allowed-tools: Bash, Read, Glob, Grep, Write, Edit, Agent
argument-hint: "<ticket or delivery objective>"
---

# Delegated Delivery

Use a layered execution model:

- main PM owns scope, sequencing, and final acceptance
- sub-PM owns one ticket end to end
- implementation worker makes the scoped change
- reviewer looks for real risk
- main PM accepts or sends the ticket back

`references/SOP.md` is the canonical operating model. Read it when you are
actually running a ticket through this workflow.

Use `references/templates.md` when you need copy-paste prompt structures for:

- main PM -> sub-PM ticket packet
- sub-PM -> implementation worker brief
- sub-PM -> reviewer brief
- sub-PM -> main PM outcome packet

## Workflow

1. Decide whether the ticket is ready to delegate.
2. Assign one sub-PM as the ticket owner.
3. Have the sub-PM read the directly relevant current truth and restate the
   ticket.
4. Use one worker and one reviewer for the ticket.
5. Give the worker the ticket packet and let them take the first pass.
6. Give the reviewer the ticket contract, handoff, and changed files or diff.
7. Have the sub-PM triage findings, run final validation, and prepare the
   outcome packet.
8. Have the main PM accept or send the ticket back.

When spawning subagents, pass ticket-local context plus the directly relevant
sources of truth. Do not preload unrelated tickets or broad program context.
