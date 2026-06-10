# Markdown and Skill Repositories

Documentation-heavy repos need a lighter quality profile than application repos.
Set up checks that catch broken structure and formatting drift without forcing a
large unrelated prose rewrite.

## Recommended tools

- `markdownlint-cli2` for Markdown structure linting
- Prettier for intentional Markdown/YAML/JSON formatting
- A small repo-specific validation script when docs have domain invariants
  such as `SKILL.md` frontmatter, README tables, or marketplace manifests

Use `remark-lint` only when the repo needs AST-aware or custom Markdown rules
that markdownlint cannot express.

## Configure deliberately

Do not accept default Markdown rules blindly. In particular:

- `MD013` line length defaults to 80 and includes code blocks, headings, and
  tables unless configured.
- `MD040` requires every fenced block to specify a language; useful in code
  docs, noisy in prompt examples.
- `MD010` can flag tabs inside Makefile snippets unless code blocks are
  excluded.
- Prettier preserves Markdown prose wrapping by default; set `proseWrap`
  deliberately if the repo wants a different policy.

For existing docs, start with a passing lint baseline and tighten rules in
follow-up changes.

## Example package scripts

```json
{
  "scripts": {
    "format": "prettier --write \"README.md\" \"skills/**/*.md\"",
    "lint:markdown": "markdownlint-cli2 \"README.md\" \"skills/**/*.md\"",
    "check": "npm run lint:markdown"
  }
}
```

Use the detected package manager. Install current `markdownlint-cli2` and
`prettier` dev dependencies at setup time and let the project lockfile pin them.

After adding a real validation script, include it explicitly:

```json
{
  "scripts": {
    "validate": "node scripts/validate-skills.mjs",
    "check": "npm run lint:markdown && npm run validate"
  }
}
```

## Skill repo invariants

For Agent Skill repos, consider a deterministic validation script that checks:

- every `skills/<name>/SKILL.md` has frontmatter with `name` and `description`
- the frontmatter `name` matches the directory name
- marketplace/plugin metadata lists every skill directory
- README skill tables include every listed skill
- bundled scripts have tests or documented smoke commands when practical

Run this validation in CI with the rest of the non-writing checks.
