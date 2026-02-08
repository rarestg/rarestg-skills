# JavaScript/TypeScript: Biome + Knip + lefthook + tsc

## Biome

Biome handles formatting, linting, and import sorting for JS, TS, JSX, TSX, CSS, and HTML.

### Install

```bash
npm install --save-dev --save-exact @biomejs/biome
npx biome init
```

### Configure

Edit `biome.json` (created by `biome init`):

```json
{
  "$schema": "https://biomejs.dev/schemas/2.0.0/schema.json",
  "organizeImports": {
    "enabled": true
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
  }
}
```

### Usage

```bash
npx biome check .                 # lint + format check
npx biome check . --write         # lint + format + auto-fix
npx biome format . --write        # format only
npx biome lint .                  # lint only
```

## TypeScript type checking

Biome's linter catches many issues but does not replace `tsc` for full type checking.

Ensure `tsconfig.json` has strict mode enabled:

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

## Knip

Knip detects unused files, exports, dependencies, and dev dependencies.

### Install

```bash
npm install --save-dev knip
```

### Configure

Knip works zero-config for most projects. For custom setups, add `knip.json`:

```json
{
  "entry": ["src/index.ts"],
  "project": ["src/**/*.ts"],
  "ignore": ["**/*.test.ts"]
}
```

### Usage

```bash
npx knip                  # full report
npx knip --fix            # auto-remove unused exports and dependencies
```

## Standard commands

Add all scripts to `package.json` to expose the standard command contract:

```json
{
  "scripts": {
    "format": "biome check . --write",
    "lint": "biome lint .",
    "typecheck": "tsc --noEmit",
    "check": "biome check . && tsc --noEmit && knip",
    "check:fix": "biome check . --write && tsc --noEmit && knip"
  }
}
```

## Lefthook (pre-commit hooks)

Lefthook runs checks automatically before each commit.

### Install

```bash
npm install --save-dev lefthook
npx lefthook install
```

### Configure

Create `lefthook.yml` in the project root:

```yaml
pre-commit:
  parallel: true
  commands:
    biome:
      glob: "*.{js,ts,jsx,tsx,css,json}"
      run: npx biome check --write --no-errors-on-unmatched --files-ignore-unknown=true {staged_files}
      stage_fixed: true
    typecheck:
      run: npx tsc --noEmit
```

The `stage_fixed` option automatically re-stages files that Biome fixes.

### Notes

- Lefthook is fast — it runs commands in parallel by default
- The `glob` filter ensures Biome only runs on relevant file types
- Type checking runs on the full project (not just staged files) to catch cross-file issues

## Full setup sequence

For a new JS/TS project, run these in order:

```bash
# 1. Biome
npm install --save-dev --save-exact @biomejs/biome
npx biome init
# Edit biome.json with the config above

# 2. Knip
npm install --save-dev knip

# 3. Lefthook
npm install --save-dev lefthook
npx lefthook install
# Create lefthook.yml with the config above

# 4. Add scripts to package.json
# check, check:fix, format, lint, typecheck, knip

# 5. Run everything once to establish baseline
npx biome check . --write
npx tsc --noEmit
npx knip
```
