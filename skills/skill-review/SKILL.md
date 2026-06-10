---
name: skill-review
description: >-
  Review an agent skill for quality, portability, completeness, and correctness.
  Use after creating or modifying a skill, especially to check whether it
  captures a repeatable workflow, uses clear name and description metadata,
  stays lean, and places scripts, references, and assets only where useful.
---

# Skill Review

Review a skill and propose improvements only if genuinely needed. Bias toward
leaving things alone. A short, focused skill is better than a comprehensive one
that wastes tokens.

## Portable Baseline

A portable skill is a directory with:

- `SKILL.md` containing YAML frontmatter and Markdown instructions
- `name` and `description` in frontmatter
- optional `scripts/`, `references/`, and `assets/` when they earn their cost

Treat behavior-controlling frontmatter beyond `name` and `description` as
runtime-specific unless the target platform or open skill spec documents it.
Do not require platform-specific fields for a generic skill.

## Process

### 1. Read everything

Read all files in the skill directory: `SKILL.md`, scripts, references, assets,
and platform metadata if present. Note the intended runtime only if the skill or
repo declares one; do not assume Claude, Codex, or another agent by default.

### 2. State the intent

In one sentence: what problem does this skill solve, and for whom? Ground the
rest of the review in this.

### 3. First-principles check

- Is this a repeatable workflow, lesson learned, tool pattern, or local rule?
- Is a skill the simplest useful way to preserve it?
- Does the skill add value beyond what an AI agent already knows?
- Could the same value be delivered with fewer instructions or files?

### 4. Review checklist

**Portable frontmatter:**

- Does `name` match the skill directory and use short lowercase hyphen-case?
- Is `description` specific about when to use the skill?
- Does `description` front-load key trigger words and scope boundaries?
- If extra frontmatter exists, is it documented for the target runtime or used
  only as portable metadata?
- Are platform-specific behavior fields intentional rather than cargo-culted?

**Body:**

- Under 500 lines? If over, move detail to reference files.
- Does every paragraph justify its token cost?
- Are instructions concrete and actionable?
- Does it capture inputs, repeatable steps, decisions, gotchas, and expected
  output where those matter?
- Does it avoid generic advice an agent already knows?
- If files are referenced, is it clear when to load or use them?

**Progressive disclosure:**

- Is `SKILL.md` doing too much?
- Should long schemas, examples, policies, or variant-specific details move to
  directly linked files under `references/`?
- Would a bundled script be more reliable than prose instructions? Use scripts
  when the agent would otherwise regenerate the same fragile code each time.

**Resources:**

- Scripts: do they actually run, and are they necessary?
- References: are they discoverable from `SKILL.md`, non-duplicative, and loaded
  only when useful?
- Assets: are they output materials or templates rather than prose docs?
- Are there auxiliary files that add clutter, such as extra READMEs, changelogs,
  quick references, or notes about how the skill was created?

**Portability:**

- Does the skill avoid confusing skills with repo instructions such as
  `AGENTS.md`, custom prompts, slash commands, or plugin packaging?
- If the skill intentionally targets one runtime, does it say so clearly?
- If the skill is meant to be generic, can another agent use the core workflow
  from `SKILL.md` without relying on vendor-only fields?

### 5. Ask clarifying questions

Ask only when ambiguity would change the review: target runtime, intended users,
side effects, required outputs, or whether supporting files are available.

### 6. Present findings

Summarize:

1. The skill's purpose in one sentence.
2. What is working well.
3. Specific issues found, if any.
4. Proposed changes with rationale for each.

If no changes are needed, say "No changes recommended" and stop. Do not
manufacture improvements.

### 7. Apply changes only when asked

Do not edit, stage, commit, or push from a review request unless the user
explicitly asks for implementation.
