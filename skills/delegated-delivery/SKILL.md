---
name: delegated-delivery
description: >-
  Run a meaningful coding ticket through a delegated delivery workflow:
  tighten the ticket, assign one ticket owner, delegate implementation, get
  an independent review, scan for high-value simplification, validate the
  result, and return a compact outcome packet. Use when the user wants
  structured agent execution with clear scope, ownership, and review rather
  than a single-pass
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
- bounded maintainability pass checks for high-value simplification before
  closeout
- main PM accepts or sends the ticket back

`references/SOP.md` is the canonical operating model. Read it when you are
actually running a ticket through this workflow.

Dispatch prompts may be free-form, but must preserve the ticket contract:
problem, invariants, scope, non-goals, source-of-truth order, acceptance
criteria, validation, and escalation triggers.

## Workflow

1. Decide whether the ticket is ready to delegate.
2. Assign one sub-PM as the ticket owner.
3. Have the sub-PM read the directly relevant current truth and restate the
   ticket.
4. Default to one worker and one reviewer unless the ticket shape clearly
   warrants otherwise.
5. Give the worker the ticket packet and let them take the first pass.
6. Give the reviewer the ticket contract, handoff, and changed files or diff.
7. Have the sub-PM triage review findings and loop fixes as needed.
8. Run a bounded maintainability pass and accept only simplifications that
   clearly reduce complexity or risk.
9. Have the sub-PM run final validation and prepare the
   outcome packet.
10. Have the main PM accept or send the ticket back.

When spawning subagents, pass ticket-local context plus the directly relevant
sources of truth. Do not preload unrelated tickets or broad program context.
