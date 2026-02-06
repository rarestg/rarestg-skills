# rarestg-skills

Personal collection of [Agent Skills](https://agentskills.io).

## Install

```
/plugin marketplace add rarestg/rarestg-skills
/plugin install rarestg-skills@rarestg-skills
```

## Skills

| Skill | Description |
|-------|-------------|
| [merge-stack](skills/merge-stack/) | Merge a linear stack of GitHub PRs into main one by one |
| [skill-review](skills/skill-review/) | Review a skill for quality, completeness, and correctness |

---

## Creating a new skill

### Structure

Every skill is a directory with a `SKILL.md` entrypoint. Optionally include scripts, references, and assets:

```
skill-name/
├── SKILL.md              # Required. Frontmatter + instructions.
├── references/           # Detailed docs the agent reads on demand
│   ├── api.md
│   └── schema.md
├── scripts/              # Executable code the agent runs via bash
│   └── transform.py
└── assets/               # Files used in output (templates, images, fonts)
    └── template.html
```

### SKILL.md

Two parts: YAML frontmatter and markdown body.

```yaml
---
name: my-skill                      # Lowercase, hyphens, max 64 chars. Becomes /my-skill.
description: >-                     # Max 1024 chars. This is the ONLY thing the agent sees
  What this skill does and when      # at startup — it drives auto-triggering. Be specific
  to use it. Include trigger phrases # about triggers and use cases.
  and concrete scenarios.
disable-model-invocation: true      # Only user can invoke via /my-skill. Use for side-effects.
allowed-tools: Bash(gh *), Read     # Restrict tools when skill is active.
context: fork                       # Run in isolated subagent (no conversation history).
agent: Explore                      # Subagent type when context: fork. Default: general-purpose.
argument-hint: "[issue-number]"     # Shown in autocomplete.
---

Instructions go here. Keep under 500 lines.
Reference supporting files so the agent knows they exist:

- For API details, see [api.md](references/api.md)
- For the schema, see [schema.md](references/schema.md)
```

### Frontmatter fields

| Field | Default | Purpose |
|-------|---------|---------|
| `name` | directory name | Slash command name |
| `description` | first paragraph | When the agent should use this skill |
| `disable-model-invocation` | `false` | `true` = manual `/name` only, no auto-trigger |
| `user-invocable` | `true` | `false` = hidden from `/` menu, agent-only |
| `allowed-tools` | all | Comma-separated tool restrictions |
| `context` | inline | `fork` = run in isolated subagent |
| `agent` | `general-purpose` | Subagent type when `context: fork` |
| `model` | inherited | Override model for this skill |
| `argument-hint` | none | Autocomplete hint for expected args |

### Progressive disclosure

Context is expensive. Skills load in three levels — only pay for what you use:

**Level 1 — Metadata (always loaded, ~100 tokens):** The `description` from frontmatter. This is how the agent decides whether to trigger the skill. Put all "when to use" info here, not in the body.

**Level 2 — SKILL.md body (loaded when triggered, <5k tokens):** Instructions, workflows, examples. Keep it lean. Link to reference files for details rather than inlining everything.

**Level 3 — Bundled files (loaded as needed, unlimited):** The agent reads reference files or executes scripts only when the task requires them. Scripts run via bash and only their output enters context — the source code never does.

```
User asks something → Agent checks descriptions (Level 1)
                    → Matches skill, reads SKILL.md (Level 2)
                    → Task needs schema? Reads references/schema.md (Level 3)
                    → Task needs transform? Runs scripts/transform.py (Level 3)
```

### Arguments and dynamic context

Use `$ARGUMENTS` (or `$0`, `$1`, `$2`) for positional args:

```yaml
---
name: fix-issue
---
Fix GitHub issue $0 following our coding standards.
```

`/fix-issue 123` → "Fix GitHub issue 123 following our coding standards."

Use `` !`command` `` to inject shell output before the agent sees the prompt:

```yaml
---
name: pr-summary
---
## PR diff
!`gh pr diff`

Summarize this pull request.
```

### Design guidelines

1. **Only add what the agent doesn't already know.** AI agents are smart. Don't explain how git works — explain your specific workflow.
2. **Match freedom to fragility.** Open field (many valid approaches) → text guidance. Narrow bridge (must be exact) → specific scripts or commands.
3. **One file per concern.** Don't put API docs, schemas, and examples in SKILL.md. Split them into reference files and link from SKILL.md.
4. **Scripts for reliability.** If the agent would rewrite the same code every time, bundle it as a script. Scripts are token-efficient and deterministic.
5. **Test scripts by running them.** Don't assume they work — execute them.
6. **`disable-model-invocation: true` for anything destructive.** Deploys, merges, sends, deletes — always manual.

### Adding a skill to this repo

1. Create `skills/<skill-name>/SKILL.md` (plus any supporting files)
2. Add `"./skills/<skill-name>"` to the `skills` array in `.claude-plugin/marketplace.json`
3. Commit and push
4. Run `/plugin marketplace update` to pull the latest
