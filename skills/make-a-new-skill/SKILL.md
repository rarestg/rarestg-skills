---
name: make-a-new-skill
description: >-
  Create or update a concise agent skill from a repeated workflow, lesson
  learned, SOP, tool pattern, or source notes. Use when asked to make a new
  skill, improve an existing skill, write a SKILL.md, turn instructions into a
  skill, capture what was learned as a reusable skill, add a skill to this repo,
  or package a repeatable agent workflow. Triggers on: "create a skill", "write
  a skill", "make this a skill", "turn this into a skill", "turn this into a
  SKILL.md", "make a new skill", "update this skill", "add a new skill".
---

# Make a New Skill

A skill is a short, reusable SOP that helps an AI agent or human repeat a task
well next time. Make one when you finish something and think: "I learned a
process here that I will probably need again."

The goal is not to document everything. The goal is to capture the useful steps,
decisions, shortcuts, tools, and gotchas so the next attempt is faster and
better.

## When to Make One

Make or update a skill when the work is:

- repeated or likely to recur
- multi-step enough that sequence matters
- easy to drift on in tone, format, or quality
- dependent on local conventions, tools, schemas, or examples
- valuable because of lessons learned during the last attempt

Do not make a skill for one-off facts, generic advice, or a workflow the agent
can already do reliably without local guidance.

## Workflow

### 1. Gather concrete examples

Before choosing the structure, understand how the skill will be used. Collect
two or three concrete user requests, source notes, or likely examples. If the
user provided only one example, infer adjacent examples and ask only if the
uncertainty changes the skill's scope or safety.

### 2. Name the skill

Use a short, clear, lowercase name with hyphens:

```text
write-client-proposals
clean-survey-data
prepare-podcast-notes
make-study-guide
```

Prefer a verb phrase that says what the skill helps do.

### 3. Write when to use it

The frontmatter `description` is the trigger surface. It is what helps the skill
get chosen later, so make it specific:

- what task the skill handles
- when it should be used
- concrete phrases the user might say
- when not to use it, if misuse is likely

Use portable frontmatter by default:

- `name` matches the directory and uses lowercase hyphen-case.
- `description` explains what the skill does, when to use it, and when not to
  use it if misuse is likely.

Treat behavior controls as runtime-specific. Invocation policy, tool
permissions, argument hints, subagents, hooks, shell injection, and UI visibility
vary between agents. Add those fields only when the skill intentionally targets a
runtime that documents them.

For destructive workflows, use the target runtime's explicit-invocation,
permission, or policy mechanism. Do not treat a generic `SKILL.md` body as a
safety boundary.

### 4. Capture the repeatable workflow

Write the steps someone should follow next time. Keep it practical. Do not
explain obvious things; focus on what made the task work.

Good workflow steps usually capture:

- the order of operations
- required inputs
- commands or tools whose exact shape matters
- decisions the agent must make consistently
- the expected final output

Match specificity to fragility: use prose when many approaches are valid, and
use exact commands or scripts when the task is repetitive, fragile, or easy to
get wrong.

### 5. Add lessons, decisions, and gotchas

This is often the most valuable part of the skill. Capture what future-you might
forget:

- common mistakes to avoid
- shortcuts that worked
- assumptions that must be checked
- local naming, formatting, or review conventions
- edge cases that changed the approach
- final quality checks before completion

### 6. Add resources only when needed

Use one `SKILL.md` by default. Add bundled files only when they earn their
cost:

- `references/` for longer guidance, schemas, rules, or examples the agent
  should read on demand.
- `scripts/` for deterministic code the agent should run instead of rewriting.
- `assets/` for templates, images, logos, starter files, or output materials.

If the main instructions are enough, do not add extra files.

If the skill has variants, keep selection guidance in `SKILL.md` and move
variant-specific detail into directly linked `references/` files.

Do not add auxiliary docs such as `README.md`, installation guides, quick
references, changelogs, or notes about how the skill was created.

### 7. Keep the shape flexible

Common useful sections are `Purpose`, `Inputs`, `Workflow`, `Rules`,
`Output Format`, `Gotchas`, and `Resources`. Use only the sections that help.
Do not force a rigid template if another organization is clearer.

### 8. Wire it into this repo

When adding a skill here:

1. Create `skills/<skill-name>/SKILL.md`.
2. Add `"./skills/<skill-name>"` to `.claude-plugin/marketplace.json`.
3. Add one README table row with a short description.

### 9. Test it on a real example

Try the skill against a real task or source note. Ask:

- Did it trigger for the right situation?
- Were the steps clear?
- Was anything important missing?
- Was anything too wordy?
- Would this save time next time?

Then revise. Run `/skill-review skills/<skill-name>` or apply the same checklist
manually before calling the skill done.

## Quality Bar

A good skill is lean and practical. It answers:

- When should I use this?
- What do I need?
- What steps should I follow?
- What did we learn last time?
- What mistakes should I avoid?
- What should the final result look like?

A good skill is not a manual. It is a reusable shortcut from experience.
