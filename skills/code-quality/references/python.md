# Python: Ruff + type checking + pre-commit

Use the project's existing Python manager. The examples prefer `uv`; adapt to
Poetry, Hatch, pip, or the existing runner when the repo already uses one.

## Ruff

Ruff handles formatting, linting, and import sorting in a single tool.

### Install Ruff

```bash
# In pyproject.toml projects
uv add --dev ruff

# Or with pip
python -m pip install ruff
```

### Configure Ruff

Add to `pyproject.toml`:

```toml
[tool.ruff]
target-version = "py312"   # adjust to the project's minimum Python version
line-length = 88

[tool.ruff.lint]
select = [
    "E",    # pycodestyle errors
    "W",    # pycodestyle warnings
    "F",    # pyflakes
    "I",    # isort (import sorting)
    "N",    # pep8-naming
    "UP",   # pyupgrade
    "B",    # flake8-bugbear
    "SIM",  # flake8-simplify
    "TCH",  # flake8-type-checking
    "RUF",  # ruff-specific rules
]

[tool.ruff.lint.isort]
known-first-party = ["mypackage"]  # replace with actual package name
```

For existing projects, start with a smaller passing baseline if the strict rule
set creates hundreds of unrelated errors. Add stricter rules incrementally.

### Use Ruff

```bash
ruff check .                  # lint
ruff check . --fix            # lint + safe autofixes
ruff format .                 # format
ruff format --check .         # verify formatting without writing
ruff check . --select I --fix # sort imports only
```

Run `ruff check --fix` before `ruff format` when using both fixers.

## Type checking

Use the type checker that matches the project.

### mypy

```bash
uv add --dev mypy
uv run mypy .
```

For new projects, strict mypy is a good default:

```toml
[tool.mypy]
strict = true
warn_return_any = true
warn_unused_configs = true
```

For existing projects, adopt strict mode incrementally instead of creating a
large unrelated error baseline.

### Pyright

Pyright is fast, but strictness requires config. The PyPI package is a
community-maintained wrapper around the Node-based Pyright distribution; use it
only when that fits the project.

```bash
uv add --dev pyright
uv run pyright
```

```toml
[tool.pyright]
typeCheckingMode = "strict"
pythonVersion = "3.12"
```

## Pre-commit hooks

Use the `pre-commit` framework to run fast checks automatically.

### Install pre-commit

```bash
uv add --dev pre-commit
uv run pre-commit install
```

### Configure pre-commit

Create `.pre-commit-config.yaml` in the project root. Look up the current
`ruff-pre-commit` revision before writing the file. Pin that concrete revision,
then keep it fresh with `pre-commit autoupdate` or Dependabot's `pre-commit`
ecosystem.

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: vX.Y.Z # replace with the current ruff-pre-commit release
    hooks:
      - id: ruff-check
        args: [--fix]
      - id: ruff-format
```

Do not use isolated type-checker mirrors as a generic default. For example,
`pre-commit/mirrors-mypy` runs in its own virtualenv and cannot see project
dependencies unless separately configured. Prefer running type checks in the
project environment, usually in CI or pre-push:

```yaml
repos:
  - repo: local
    hooks:
      - id: mypy
        name: mypy
        entry: uv run mypy .
        language: system
        pass_filenames: false
```

### First run

```bash
uv run pre-commit run --all-files
```

## Standard commands

Add a `Makefile` or equivalent project-runner tasks to expose the standard
command contract. Makefile recipe lines must use tabs, not spaces.

The indented recipe lines below must begin with literal tab characters.

```makefile
.PHONY: format lint typecheck test check check\:fix

format:
	ruff check . --fix
	ruff format .

lint:
	ruff check .
	ruff format --check .

typecheck:
	mypy .

test:
	python -m unittest discover

check: lint typecheck test

check\:fix:
	$(MAKE) format
	$(MAKE) check
```

If the repo uses `uv`, wrap tools with `uv run`. If it uses another runner, keep
that runner consistent.

## CI

CI should run non-writing checks:

```bash
make check
```

If no `Makefile` exists, run the underlying commands directly:

```bash
ruff check .
ruff format --check .
mypy .
python -m unittest discover
```

Use the current `actions/checkout` and `actions/setup-python` major versions
when adding GitHub Actions. Run type checkers inside the project environment so
they can see installed dependencies and stubs.
