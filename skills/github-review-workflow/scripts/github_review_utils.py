from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any

PR_URL_PATTERN = re.compile(
    r"^https://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/pull/(?P<number>\d+)(?:/.*)?$"
)

MISSING_METADATA_VALUES = {"", "n/a", "none", "null"}
REVIEW_ITEM_TOP_SECTION_END = "---"
DEFAULT_OUT_ROOT = Path(".github-review-workflow")
LEGACY_OUT_ROOT = Path("GitHub Reviews")
STATE_SOURCE = "status_folders_and_reply_queue_records"

LEGACY_ROOT_ERROR = (
    "Legacy GitHub review workflow root exists at 'GitHub Reviews', but the "
    "default root is now '.github-review-workflow'. Pass "
    "--out-root 'GitHub Reviews' to continue using the legacy root, or move "
    "or export state to '.github-review-workflow'."
)

RESOLVE_REVIEW_THREAD_MUTATION = """\
mutation($threadId: ID!) {
  resolveReviewThread(input: { threadId: $threadId }) {
    thread {
      id
      isResolved
    }
  }
}
"""


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


def resolve_review_out_root(out_root: str | None, *, cwd: Path | None = None) -> Path:
    if out_root is not None:
        return Path(out_root)

    base = cwd or Path.cwd()
    default_path = base / DEFAULT_OUT_ROOT
    legacy_path = base / LEGACY_OUT_ROOT
    if legacy_path.exists() and not default_path.exists():
        raise RuntimeError(LEGACY_ROOT_ERROR)
    return DEFAULT_OUT_ROOT


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


def parse_review_item_metadata(
    path: Path,
    *,
    required_keys: list[str] | tuple[str, ...] = (),
) -> dict[str, str]:
    content = path.read_text(encoding="utf-8")
    top_section = content.split(f"\n{REVIEW_ITEM_TOP_SECTION_END}\n", 1)[0]
    metadata: dict[str, str] = {}

    for line in top_section.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()

    missing = [key for key in required_keys if not metadata_value_present(metadata.get(key))]
    if missing:
        raise ValueError(f"Review item file is missing required metadata: {', '.join(missing)}")

    return metadata


def post_review_reply(
    *,
    owner: str,
    repo: str,
    pull_number: int,
    comment_database_id: str,
    reply_body: str,
) -> dict[str, Any]:
    return run_json(
        [
            "gh",
            "api",
            f"repos/{owner}/{repo}/pulls/{pull_number}/comments/{comment_database_id}/replies",
            "-X",
            "POST",
            "-f",
            f"body={reply_body}",
        ]
    )


def reply_url_from_response(response: dict[str, Any]) -> str | None:
    html_url = response.get("html_url")
    if isinstance(html_url, str) and html_url:
        return html_url
    url = response.get("url")
    if isinstance(url, str) and url:
        return url
    return None


def resolve_review_thread(thread_id: str) -> dict[str, Any]:
    return run_json(
        [
            "gh",
            "api",
            "graphql",
            "-F",
            "query=@-",
            "-F",
            f"threadId={thread_id}",
        ],
        stdin=RESOLVE_REVIEW_THREAD_MUTATION,
    )


def resolved_thread_from_response(response: dict[str, Any]) -> dict[str, Any]:
    errors = response.get("errors")
    if errors:
        raise RuntimeError(
            "GitHub GraphQL returned errors while resolving the thread:\n"
            f"{json.dumps(errors, indent=2)}"
        )

    thread = response.get("data", {}).get("resolveReviewThread", {}).get("thread")
    if not isinstance(thread, dict):
        raise RuntimeError(
            "GitHub GraphQL resolve response did not include a thread:\n"
            f"{json.dumps(response, indent=2)}"
        )

    if thread.get("isResolved") is not True:
        raise RuntimeError(
            f"GitHub GraphQL did not mark the thread resolved:\n{json.dumps(thread, indent=2)}"
        )

    return thread
