# Delegated Delivery SOP

## Purpose

This is a lightweight operating model for layered delivery:

- a main PM owns scope, sequencing, and final acceptance
- a sub-PM owns one ticket at a time
- the sub-PM uses implementation and review support to get the ticket done
- the main PM stays out of implementation churn unless the ticket drifts,
  blocks, or comes back wrong

Use this when a ticket is meaningful enough to benefit from scoped execution
and independent review. Skip it for trivial work or work that is still too
vague to delegate.

Keep the loop sequential: one ticket at a time, one worker at a time, and one
reviewer at a time.

## Core Model

The workflow is simple:

1. the main PM defines the ticket well enough to delegate
2. the sub-PM owns the ticket end to end
3. an implementation worker makes the change
4. a reviewer looks for real risk
5. the sub-PM decides whether to fix, escalate, or close
6. the main PM accepts or sends the ticket back

The key idea is separation of concerns:

- boundary-setting stays at the top
- execution stays with the ticket owner
- review stays independent

## Roles

### Main PM

Owns:

- understanding the broader roadmap, specs, and sequencing
- deciding what ticket comes next
- deciding whether a ticket is ready to delegate
- setting the contract: problem, invariants, scope, and done condition
- final acceptance

Should avoid:

- direct worker/reviewer ping-pong
- micromanaging implementation details unless something has gone wrong

### Sub-PM

Owns:

- understanding the assigned ticket and the current truth for that area
- restating the ticket before delegating
- running the execution loop
- final validation and closeout for the ticket
- returning a compact outcome packet to the main PM

### Implementation Worker

Owns:

- making the scoped change
- updating tests and any directly affected docs in scope
- leaving enough context for review and handoff
- escalating quickly when the ticket contract appears wrong or incomplete

### Reviewer

Owns:

- checking the change against the ticket contract and current truth
- surfacing meaningful findings, not just impressions
- focusing on regressions, invariant breaks, missing tests, stale state,
  async/race issues, and contract drift

## Before Delegating

Do not delegate a ticket until it is delegation-ready.

A ticket is ready when the main PM or sub-PM can state:

- the problem being solved
- the invariants that must hold
- the likely write scope
- explicit non-goals
- what sources of truth win if docs disagree
- what "done" means in behavior terms
- what validation is required

If those are not clear, tighten the ticket first. Do not make the worker
discover the contract by accident.

## Ticket Packet

Every delegated ticket should come with a compact brief. It does not need to be
long, but it should include:

- problem
- locked invariants
- likely seam or failure path
- owned write scope
- non-goals
- source-of-truth order
- acceptance criteria
- validation requirements
- any local repo or environment rules that materially affect the work

Keep repo-specific constraints in the packet, not in the general SOP.

## Execution Loop

Default loop:

1. the sub-PM reads the ticket and the directly relevant current truth
2. the sub-PM restates the ticket in plain language
3. the sub-PM decides whether the ticket is really ready
4. the implementation worker takes the first pass
5. the reviewer checks the result for material risk
6. the sub-PM triages the review
7. if needed, fixes go back to implementation
8. follow-up review goes back to the same reviewer by default
9. once the ticket is clean enough, the sub-PM runs final validation and
   closes it out

By default, use one implementation worker and one reviewer per ticket.

## Prompting Guidance

### For the implementation worker

Give:

- the exact problem
- the invariants
- owned files or modules
- known secondary surfaces to audit if relevant
- required validation
- explicit non-goals

Do not rely on file paths alone. A good worker brief explains what must remain
true.

### For the reviewer

Give:

- the ticket
- the source-of-truth order
- the handoff or implementation summary
- the changed files or diff
- the main risk to review against

Ask for findings first, with file references, not just a high-level summary.
Keep the reviewer independent: give them the ticket contract, the handoff, and
the changed files or diff, not the worker's full execution history unless that
history is itself the subject of review.

## Review Triage

The sub-PM owns review triage. Do a local merit pass before sending work back.

For each finding, ask:

- is it grounded in the ticket contract or current truth?
- is it materially risky if left unfixed?
- is the proposed fix still inside the ticket scope?

Then choose one path:

- accept it and send a focused fix back to implementation
- reject it and record why it is not material or not correct
- escalate it because the ticket contract or source-of-truth order is unclear

## Validation And Closeout

The sub-PM owns final closeout even if the worker already ran checks.

At closeout, the sub-PM should make sure the ticket has:

- the exact validation commands and observed results
- enough handoff context for review, acceptance, or pickup if needed
- explicit residual risks
- any required doc updates
- a clean ticket-scoped commit when commits are part of the workflow

Prefer a stable ticket-local regression test as an early signal, then run the
broader required checks for the ticket.

## Outcome Packet

The main PM should get a compact, standard report:

- what changed
- reviewer outcome
- validation commands and observed results
- commit SHA if applicable
- residual risks
- doc or handoff updates

That packet should be enough for the main PM to decide whether to inspect and
accept or send the ticket back.

## Acceptance

The main PM should accept a ticket when:

- the ticket contract was actually met
- the important invariants still hold
- validation is good enough for the ticket
- the residual risks are explicit
- the result still fits the broader product and sequencing direction

The main PM should inspect the actual diff or resulting files on risky,
ambiguous, or high-impact tickets. For routine work, the main PM can rely more
heavily on the sub-PM outcome packet.

## Escalation

The sub-PM should escalate when:

- the ticket is not actually ready
- sources of truth conflict in a way the ticket did not resolve
- the worker is solving the wrong problem
- the reviewer is focused on the wrong things
- validation blockers prevent confident closeout
- the work wants to expand into adjacent tickets
- unrelated changes create a real conflict in the owned area

The main PM should intervene when needed, but otherwise keep the detailed loop
delegated.
