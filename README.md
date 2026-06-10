# rarestg-skills

Personal collection of [Agent Skills](https://agentskills.io) and SOPs for AI coding agents.

## Install

```
/plugin marketplace add rarestg/rarestg-skills
/plugin install rarestg-skills@rarestg-skills
```

## Skills

| Skill | Description |
|-------|-------------|
| [merge-stack](skills/merge-stack/) | Merge a linear stack of GitHub PRs into main one by one |
| [skill-review](skills/skill-review/) | Review a skill for quality, portability, completeness, and correctness |
| [make-a-new-skill](skills/make-a-new-skill/) | Create or update a concise agent skill from a workflow, SOP, or repeated task |
| [coding-agent](skills/coding-agent/) | Orchestrate Codex CLI and Claude Code as background assistants via tmux |
| [delegated-delivery](skills/delegated-delivery/) | Run tickets through a layered main PM -> sub-PM -> worker -> reviewer delivery loop |
| [graphify-architecture-review](skills/graphify-architecture-review/) | Use Graphify semantic graphs to analyze architecture and source-validate refactor opportunities |
| [cf-browser](skills/cf-browser/) | Browse and scrape websites via Cloudflare Browser Rendering API |
| [code-quality](skills/code-quality/) | Set up formatting, linting, type checking, and pre-commit hooks from day one |
| [task-os](skills/task-os/) | Operating protocol using Taskwarrior as the continuity layer across conversations |
| [install-skills](skills/install-skills/) | Install, discover, remove, and update agent skills via the npx skills CLI |
| [stacked-diffs](skills/stacked-diffs/) | Break large changes into small, stacked PRs using vanilla git |
| [agents-md](skills/agents-md/) | Create and maintain a concise AGENTS.md that routes agents to the repo's real sources of truth |
| [execplan](skills/execplan/) | Write a self-contained execution plan for complex, multi-step implementation work |
| [github-review-workflow](skills/github-review-workflow/) | Export a PR's inline review threads, CodeRabbit outside-diff comments, and nitpicks into clean local queues for triage and follow-through |

---

## Creating a new skill

A skill is a short, reusable SOP that helps an AI agent repeat a task well. The
portable baseline is intentionally small: a directory with `SKILL.md`,
frontmatter containing `name` and `description`, Markdown instructions, and
optional supporting files.

### Structure

Every skill is a directory with a `SKILL.md` entrypoint. Optionally include
scripts, references, and assets:

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

Two parts: YAML frontmatter and Markdown body. For a portable skill, start with
only `name` and `description`:

```yaml
---
name: my-skill                      # Lowercase, hyphens, max 64 chars.
description: >-                     # What the skill does and when to use it.
  Include trigger phrases, scope,
  and concrete scenarios.
---

Instructions go here. Keep under 500 lines.
Reference supporting files so the agent knows they exist:

- For API details, see [api.md](references/api.md)
- For the schema, see [schema.md](references/schema.md)
```

### Metadata and runtime controls

Portable frontmatter:

| Field | Purpose |
|-------|---------|
| `name` | Skill identifier. Match the directory name and use lowercase hyphen-case. |
| `description` | What the skill does and when to use it. This is the trigger surface. |

Optional portable metadata such as `license`, `compatibility`, or `metadata` can
be useful for distribution, but keep it brief.

Behavior controls are runtime-specific. Invocation policy, tool permissions,
argument substitution, subagents, hooks, shell injection, and UI visibility vary
between Codex, Claude Code, and other agents. Add those fields only when the
skill intentionally targets a runtime that documents them.

For destructive workflows such as deploys, merges, sends, deletes, or
publishing, use the target runtime's explicit-invocation, permission, or policy
mechanism. Do not treat a generic `SKILL.md` body as a safety boundary.

### Progressive disclosure

Context is expensive. Skills load in three levels — only pay for what you use:

**Level 1 — Metadata:** The skill name, description, and path. This is how the
agent decides whether to trigger the skill. Put all "when to use" info in the
description, not only in the body.

**Level 2 — SKILL.md body:** Instructions, workflows, examples. Keep it lean.
Link to reference files for details rather than inlining everything.

**Level 3 — Bundled files:** The agent reads reference files or executes scripts
only when the task requires them.

```
User asks something → Agent checks descriptions (Level 1)
                    → Matches skill, reads SKILL.md (Level 2)
                    → Task needs schema? Reads references/schema.md (Level 3)
                    → Task needs transform? Runs scripts/transform.py (Level 3)
```

### Design guidelines

1. **Capture reusable experience.** Good skills preserve repeatable steps,
   decisions, shortcuts, tools, and gotchas.
2. **Only add what the agent doesn't already know.** Don't explain general
   reasoning or common tools; explain your specific workflow.
3. **Match freedom to fragility.** Open field, many valid approaches: prose
   guidance. Fragile or exact workflow: specific commands or scripts.
4. **One file per concern.** Don't put API docs, schemas, and examples in
   `SKILL.md`. Split them into reference files and link from `SKILL.md`.
5. **Scripts for reliability.** If the agent would rewrite the same code every
   time, bundle it as a script.
6. **Avoid auxiliary docs.** Do not add extra READMEs, installation guides,
   quick references, changelogs, or notes about how the skill was created.
7. **Test on a real example.** Check that the skill triggers for the right task,
   gives clear steps, and would save time next time. Run bundled scripts.

### Adding a skill to this repo

1. Create `skills/<skill-name>/SKILL.md` (plus any supporting files)
2. Add `"./skills/<skill-name>"` to the `skills` array in `.claude-plugin/marketplace.json`
3. Add the skill to the table in `README.md`
4. Commit and push
5. Run `/plugin marketplace update` to pull the latest
