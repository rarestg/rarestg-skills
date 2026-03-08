from __future__ import annotations

import json
import re
import subprocess
from typing import Any

PR_URL_PATTERN = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)(?:/.*)?$"
)

MISSING_METADATA_VALUES = {"", "n/a", "none", "null"}


def run_command(command: list[str], stdin: str | None = None) -> str:
    process = subprocess.run(command, input=stdin, capture_output=True, text=True)
    if process.returncode != 0:
        stderr = process.stderr.strip()
        raise RuntimeError(f"Command failed: {' '.join(command)}\n{stderr}")
    return process.stdout


def run_json(command: list[str], stdin: str | None = None) -> dict[str, Any]:
    output = run_command(command, stdin=stdin)
    try:
        return json.loads(output)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Failed to parse JSON output: {error}") from error


def ensure_gh_authenticated() -> None:
    run_command(["gh", "auth", "status"])


def parse_pr_url(pr_url: str) -> tuple[str, str, int]:
    match = PR_URL_PATTERN.match(pr_url.strip())
    if not match:
        raise ValueError(
            "Expected a GitHub pull request URL like "
            "https://github.com/<owner>/<repo>/pull/<number>"
        )
    owner = match.group("owner")
    repo = match.group("repo")
    number = int(match.group("number"))
    return owner, repo, number


def metadata_value_present(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() not in MISSING_METADATA_VALUES
