# JavaScript/TypeScript: Biome + tsc + optional Knip + lefthook

Use the project's existing package manager. The examples below use `npm`;
substitute `pnpm`, `yarn`, or `bun` when the repo already uses that tool. Do not
create a second lockfile.

## Biome

Biome handles formatting, linting, and import sorting for JS, TS, JSX, TSX, CSS,
JSON, HTML, and GraphQL.

### Install Biome

```bash
npm install --save-dev --save-exact @biomejs/biome
npx biome init
```

### Configure Biome

Edit `biome.json` (created by `biome init`). Prefer the installed package schema
so the editor schema follows the pinned package version:

```json
{
  "$schema": "./node_modules/@biomejs/biome/configuration_schema.json",
  "vcs": {
    "enabled": true,
    "clientKind": "git",
    "useIgnoreFile": true
  },
  "files": {
    "ignoreUnknown": true
  },
  "formatter": {
    "enabled": true,
    "indentStyle": "space",
    "indentWidth": 2,
    "lineWidth": 100
  },
  "linter": {
    "enabled": true,
    "rules": {
      "recommended": true,
      "complexity": {
        "noUselessFragments": "warn",
        "noUselessTypeConstraint": "error"
      },
      "correctness": {
        "noUnusedImports": "error",
        "noUnusedVariables": "warn"
      },
      "style": {
        "noNonNullAssertion": "warn",
        "useConst": "error",
        "useImportType": "error"
      }
    }
  },
  "assist": {
    "enabled": true,
    "actions": {
      "source": {
        "organizeImports": "on"
      }
    }
  }
}
```

Biome v2 moved import organization from top-level `organizeImports` to
`assist.actions.source.organizeImports`.

### Use Biome

```bash
npx biome ci .                  # CI/read-only: format + lint + import checks
npx biome check . --write       # local autofix: format + lint + imports
npx biome format . --write      # format only
npx biome lint .                # lint only
```

## TypeScript type checking

Biome's linter catches many issues but does not replace `tsc` for full type
checking. For TypeScript projects, install TypeScript locally if the project
does not already depend on it:

```bash
npm install --save-dev typescript
```

For new TypeScript projects, enable strict mode:

```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true
  }
}
```

For existing projects, tighten strictness incrementally instead of creating a
large unrelated error baseline.

## Knip

Knip detects unused files, exports, dependencies, and dev dependencies. Treat it
as recommended when the JS/TS project shape is clear, not mandatory for every
repo. It can need project-specific configuration in unusual frameworks.

### Install Knip

```bash
npm init @knip/config
```

Or install manually:

```bash
npm install --save-dev knip
```

For TypeScript projects, ensure `typescript` is installed locally. Many projects
also need `@types/node`.

### Configure Knip

Knip works zero-config for many projects. For custom setups, add `knip.json`:

```json
{
  "entry": ["src/index.ts"],
  "project": ["src/**/*.ts", "src/**/*.test.ts"]
}
```

Do not ignore tests by default. Tests often prove files, exports, and
dependencies are used. Add ignores only after confirming they are real false
positives.

### Use Knip

```bash
npx knip        # full report
npx knip --fix  # auto-remove supported unused exports/dependencies; review diff
```

Do not put `knip --fix` in pre-commit hooks. Run it intentionally and inspect
the VCS diff.

## Standard commands

Add scripts to `package.json` to expose the standard command contract. Omit
`typecheck` or `unused` when they do not fit the repo:

```json
{
  "scripts": {
    "format": "biome check . --write",
    "lint": "biome ci .",
    "typecheck": "tsc --noEmit",
    "unused": "knip",
    "check": "biome ci . && tsc --noEmit && knip",
    "check:fix": "biome check . --write && npm run check"
  }
}
```

Use the detected package manager's script runner in examples and CI.

## Lefthook

Lefthook runs checks automatically before each commit.

### Install Lefthook

```bash
npm install --save-dev lefthook
npx lefthook install
```

### Configure Lefthook

Create `lefthook.yml` in the project root:

```yaml
pre-commit:
  parallel: true
  commands:
    biome:
      glob: "*.{js,jsx,ts,tsx,mjs,cjs,mts,cts,json,jsonc,css,html,graphql,gql}"
      run: npx biome check --write --no-errors-on-unmatched --files-ignore-unknown=true {staged_files}
      stage_fixed: true
```

Use pre-push for slower full-project checks when desired:

```yaml
pre-push:
  commands:
    check:
      run: npm run check
```

### Notes

- `parallel: true` opts in to parallel command execution.
- `stage_fixed: true` re-stages files fixed by the hook.
- Type checking runs on the full project, so it is usually better in CI or
  pre-push than in pre-commit.

## CI

CI should run non-writing checks:

```bash
npm run check
```

If there is no `check` script yet, run the underlying commands directly:

```bash
npx biome ci .
npx tsc --noEmit
npx knip
npm test
```

Use the current `actions/checkout` and `actions/setup-node` major versions when
adding GitHub Actions, and enable package-manager cache only for the detected
package manager.

## Full setup sequence

For a new JS/TS project, run these in order:

```bash
# 1. Biome
npm install --save-dev --save-exact @biomejs/biome
npx biome init
# Edit biome.json with the config above.

# 2. TypeScript, if applicable
npm install --save-dev typescript

# 3. Knip, if useful for the project shape
npm init @knip/config

# 4. Lefthook
npm install --save-dev lefthook
npx lefthook install
# Create lefthook.yml with the config above.

# 5. Add scripts to package.json
# format, lint, check, check:fix; typecheck/unused/test when relevant.

# 6. Run everything once to establish the baseline
npx biome check . --write
npx tsc --noEmit
npx knip
npm test
```
