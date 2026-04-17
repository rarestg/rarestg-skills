# Delegated Delivery Templates

Use these as compact starting points. Keep them short enough that the receiver
can act without hunting for the real contract.

## Main PM -> Sub-PM Ticket Packet

```text
Ticket:

Problem:

Locked invariants:

Likely seam or failure path:

Owned write scope:

Non-goals:

Source-of-truth order:

Acceptance criteria:

Validation required:

Repo / environment rules:

Escalate if:
```

## Sub-PM -> Implementation Worker Brief

```text
You own the implementation pass for this ticket.

Problem:

Locked invariants:

Owned files / modules:

Secondary surfaces to audit:

Non-goals:

Required validation:

Escalate immediately if:
```

Expected worker handoff:

```text
What changed:

Files touched:

Validation commands and observed results:

Open questions:

Residual risks:
```

## Sub-PM -> Reviewer Brief

```text
Review this ticket for material risk.

Ticket:

Source-of-truth order:

Implementation summary:

Changed files / diff:

Main risk to review against:

Return findings first with file references. Focus on regressions, invariant
breaks, missing tests, stale state, async/race issues, and contract drift.
```

Suggested reviewer response:

```text
Findings:
- path:line - issue

Open questions:

Residual risks:
```

## Sub-PM -> Main PM Outcome Packet

```text
Ticket:

What changed:

Reviewer outcome:

Validation commands and observed results:

Commit / branch (optional) / PR (optional):

Residual risks:

Docs / handoff updates:

Decision requested:
```
