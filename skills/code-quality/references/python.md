# Python: Ruff + pre-commit

## Ruff

Ruff handles formatting, linting, and import sorting in a single tool.

### Install

```bash
# In pyproject.toml projects (preferred)
uv add --dev ruff

# Or with pip
pip install ruff
```

### Configure

Add to `pyproject.toml`:

```toml
[tool.ruff]
target-version = "py312"   # adjust to project's minimum Python version
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

### Usage

```bash
ruff check .              # lint
ruff check . --fix        # lint + auto-fix
ruff format .             # format
ruff check . --select I --fix  # sort imports only
```

## Type checking

Use the type checker that matches the project:

```bash
# mypy (most common)
uv add --dev mypy
mypy .

# pyright (faster, stricter)
uv add --dev pyright
pyright
```

Add basic mypy config to `pyproject.toml` if using mypy:

```toml
[tool.mypy]
strict = true
warn_return_any = true
warn_unused_configs = true
```

## Pre-commit hooks

Use the `pre-commit` framework to run checks automatically.

### Install

```bash
uv add --dev pre-commit
pre-commit install
```

### Configure

Create `.pre-commit-config.yaml` in the project root:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.9.6  # use latest version
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
  - repo: https://github.com/pre-commit/mirrors-mypy
    rev: v1.14.1  # use latest version
    hooks:
      - id: mypy
        additional_dependencies: []  # add typed stubs as needed
```

### First run

```bash
pre-commit run --all-files   # verify everything passes
```

## Standard commands

Add a `Makefile` to expose the standard command contract:

```makefile
.PHONY: format lint typecheck check check\:fix

format:
	ruff format .
	ruff check . --select I --fix

lint:
	ruff check .

typecheck:
	mypy .

check: lint typecheck

check\:fix:
	ruff check . --fix
	$(MAKE) format
	$(MAKE) check
```
