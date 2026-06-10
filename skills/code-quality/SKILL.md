---
name: code-quality
description: >-
  Set up formatting, linting, import sorting, type checking, tests, CI handoff,
  and pre-commit hooks when scaffolding or starting a new project. Use this
  skill whenever creating a new project, initializing a repo, scaffolding an
  app, or when the user asks to add linting/formatting/testing to an existing
  project. Triggers on: "new project", "scaffold", "init", "set up linting",
  "add formatter", "add pre-commit hooks", "configure biome", "configure ruff",
  "set up CI". The goal is to establish quality tooling from day one so issues
  are caught incrementally, not in a painful bulk-fix later.
---

# Code Quality Setup

When starting or scaffolding a project, set up formatting, linting, import
sorting, type checking, tests, and local hooks before writing much application
code. This prevents the painful scenario of adding these tools later and facing
thousands of lines of formatting changes in a single commit.

Keep this skill focused on local quality tooling and quality gates. Do not add
deployment, preview environments, release automation, rollback flows, feature
flags, or broader organization process here.

## Detect the ecosystem

Determine the project type from existing files or the scaffolding context:

| Signal                                                        | Ecosystem                                                    |
| ------------------------------------------------------------- | ------------------------------------------------------------ |
| `pyproject.toml`, `setup.py`, `requirements.txt`, `.py` files | Python                                                       |
| `package.json`, `tsconfig.json`, `.ts`/`.js`/`.tsx` files     | JavaScript/TypeScript                                        |
| `SKILL.md`, many `.md` files, marketplace/plugin metadata     | Documentation or skill repo                                  |
| Multiple signals                                              | Monorepo or mixed repo - configure each ecosystem separately |

Also check for existing quality tooling configs (`.eslintrc`, `.prettierrc`,
`biome.json`, `[tool.black]` or `[tool.ruff]` in `pyproject.toml`,
`.pre-commit-config.yaml`, `lefthook.yml`, `Makefile`, CI workflows). If present,
preserve them. Only migrate to different tools if the user explicitly requests
it.

## Detect package managers and runners

Use the repo's existing toolchain instead of introducing a new one:

- JS/TS: detect `pnpm-lock.yaml`, `yarn.lock`, `bun.lock`/`bun.lockb`, or
  `package-lock.json`; use the matching package manager for installs and
  scripts.
- Python: prefer the existing project manager (`uv`, Poetry, Hatch, pip, etc.).
- Monorepos: run commands from the correct package or workspace root.

Do not create a second lockfile.

## Set up tooling

After detecting the ecosystem, follow the appropriate guide:

- **Python projects** - see [python.md](references/python.md) for Ruff, type
  checking, and pre-commit setup
- **JS/TS projects** - see [javascript.md](references/javascript.md) for Biome,
  TypeScript, optional Knip, and lefthook setup
- **Documentation or skill repos** - see [markdown.md](references/markdown.md)
  for Markdown linting, formatting policy, and skill-repo validation ideas

## Standard command contract

Expose a small, predictable command surface through `package.json` scripts,
`Makefile`, or the project's existing task runner:

| Command     | What it does                                                                            |
| ----------- | --------------------------------------------------------------------------------------- |
| `format`    | Auto-format and sort imports                                                            |
| `lint`      | Lint and format-check without writing                                                   |
| `typecheck` | Run type checker when the ecosystem supports it                                         |
| `test`      | Run deterministic tests                                                                 |
| `check`     | All non-writing checks: lint, typecheck, tests, and unused-code detection when relevant |
| `check:fix` | Run autofixers, then run `check`                                                        |

Do not invent fake commands for docs-only or tiny repos. If an ecosystem has no
meaningful type checker or unused-code detector, omit that command or make
`check` call only the commands that exist.

## Hook policy

Pre-commit hooks should be fast and should prefer staged-file autofixers. Full
project checks (`check`) should run before completion and in CI.

Avoid putting slow full-repo checks in pre-commit unless the project is small or
the user explicitly wants strict hooks. Type checking, unused-code detection,
and full test suites usually belong in CI or pre-push hooks.

## CI handoff

If CI already exists, ensure it runs the standard non-writing check command:

- JS/TS: the detected package manager's `check` script
- Python: `make check` or the project runner's equivalent
- Monorepo: each package/ecosystem check from the right workspace root

If CI does not exist and either the user asked for CI or the task is broad
project scaffolding/setup, add a minimal workflow that runs lint, typecheck,
tests, and build only when those commands exist. If the user asked only for
local linting/formatting, mention CI as a follow-up instead of adding it
automatically. For GitHub Actions, workflows live under `.github/workflows`;
check the current official action versions before writing a new workflow.

When CI fails, read the exact failing command and output, reproduce that command
locally, fix the issue, and rerun the relevant check before claiming completion.

Mention branch protection or required status checks as a follow-up when useful,
but leave deploy pipelines, preview environments, and release automation to a
CI/CD-specific workflow.

## Workflow

1. Install and configure the tools for the detected ecosystem.
2. Add hook infrastructure if appropriate (`lefthook` or `pre-commit`).
3. Add or update CI when it is in scope so central checks run the non-writing
   command.
4. Run the full suite once to establish a clean baseline.
5. Fix initial issues so the first "real" commit starts clean.
6. Commit configuration and mechanical baseline changes separately when
   practical.

## When working on existing projects

If a project already has code but no quality tooling:

1. Add and configure the tools.
2. Run the formatter first and commit the formatting changes separately with a
   message like `chore: apply initial formatting`.
3. Run the linter and fix issues separately: `chore: fix initial lint issues`.
4. Wire up hooks and CI last so all future changes are checked.

For existing projects, adopt strict type checking incrementally. Prefer a clean,
useful baseline over flipping every strict option at once and generating
hundreds of unrelated errors.

## Guardrails

- **Don't replace existing mature tooling.** If a project already uses
  ESLint/Prettier, Black, or other established tools, keep them. Only migrate to
  Biome/Ruff if the user explicitly asks.
- **Don't create duplicate tooling.** Avoid ESLint + Biome, Black + Ruff
  formatter, or multiple hook managers unless the project already uses them
  intentionally.
- **Don't broadly disable rules to force a green baseline.** Use narrow,
  targeted exceptions (`// biome-ignore`, `# noqa: XX`) with comments explaining
  why.
- **Don't run broad autofixers on generated files.** Preserve generated,
  vendored, build-output, snapshot, lockfile, and migration files unless the
  project already includes them in quality tooling.
- **If tooling binaries aren't available, scaffold configs anyway.** Write the
  configuration files and report the exact install/check commands the user
  still needs to run.
- **Don't copy package versions from this skill blindly.** At setup time,
  install the current appropriate version with the detected package manager and
  let the project lockfile pin it. For pre-commit hooks, look up the current
  hook revision before writing `.pre-commit-config.yaml`.

## Completion checklist

Before considering the setup done, verify:

1. Formatter, linter, tests, and type checker installed and configured where
   relevant
2. Import sorting enabled (Ruff's `I` rules or Biome's `organizeImports`)
3. Standard commands work for the repo shape: `format`, `lint`, `test`,
   `typecheck` when relevant, `check`, and `check:fix`
4. Hooks configured and executable when requested (`pre-commit run --all-files`
   or the detected runner equivalent, for example `npx lefthook run pre-commit`)
5. CI runs the non-writing check command when CI is in scope
6. Baseline autofix applied and a clean check passes with no errors
