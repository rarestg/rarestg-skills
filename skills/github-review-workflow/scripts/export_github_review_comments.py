#!/usr/bin/env python3
"""
Export clean GitHub PR review comments into local files under `GitHub Reviews/`
in the current working project.

The export intentionally treats inline review threads as the actionable queue and
only saves the CodeRabbit walkthrough as optional context.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from comment_formatters import extract_comment_title, sanitize_comment_text
from github_review_utils import (
    ensure_gh_authenticated,
    metadata_value_present,
    parse_pr_url,
    run_json,
)

GRAPHQL_QUERY = """\
query(
  $owner: String!,
  $repo: String!,
  $number: Int!,
  $commentsCursor: String,
  $reviewsCursor: String,
  $threadsCursor: String,
  $fetchComments: Boolean!,
  $fetchReviews: Boolean!,
  $fetchThreads: Boolean!
) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $number) {
      number
      title
      url
      state

      comments(first: 100, after: $commentsCursor) @include(if: $fetchComments) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          body
          bodyText
          createdAt
          url
          author { login }
        }
      }

      reviews(first: 100, after: $reviewsCursor) @include(if: $fetchReviews) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          state
          body
          bodyText
          submittedAt
          url
          author { login }
        }
      }

      reviewThreads(first: 100, after: $threadsCursor) @include(if: $fetchThreads) {
        pageInfo { hasNextPage endCursor }
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          originalLine
          comments(first: 100) {
            pageInfo { hasNextPage endCursor }
            nodes {
              id
              fullDatabaseId
              body
              bodyText
              createdAt
              url
              author { login }
            }
          }
        }
      }
    }
  }
}
"""

DISPATCH_GUIDANCE = """# Dispatch Guidance

- Start with a fresh context.
- Read this file, the assigned review item, `01-coderabbit-walkthrough.md` if present, and only the code needed to evaluate that item.
- Reassess whether the comment has merit before editing.
- If valid, implement the smallest defensible fix.
- If not worth taking, make no code change and explain why.
- Do not address any other review item.
- Do not widen scope or touch files outside the assigned ownership unless the parent agent explicitly expands scope.
- Preserve unrelated user changes in the worktree.
"""

OUT_ROOT_GITIGNORE = "*\n!.gitignore\n"
LEGACY_OUT_ROOT_GITIGNORE = "*\n!.gitignore\n!SOP.md\n"
REVIEW_ITEM_TOP_SECTION_END = "---"


def graphql_fetch(
    owner: str,
    repo: str,
    number: int,
    *,
    fetch_comments: bool,
    fetch_reviews: bool,
    fetch_threads: bool,
    comments_cursor: str | None = None,
    reviews_cursor: str | None = None,
    threads_cursor: str | None = None,
) -> dict[str, Any]:
    command = [
        "gh",
        "api",
        "graphql",
        "-F",
        "query=@-",
        "-F",
        f"owner={owner}",
        "-F",
        f"repo={repo}",
        "-F",
        f"number={number}",
        "-F",
        f"fetchComments={'true' if fetch_comments else 'false'}",
        "-F",
        f"fetchReviews={'true' if fetch_reviews else 'false'}",
        "-F",
        f"fetchThreads={'true' if fetch_threads else 'false'}",
    ]
    if comments_cursor:
        command += ["-F", f"commentsCursor={comments_cursor}"]
    if reviews_cursor:
        command += ["-F", f"reviewsCursor={reviews_cursor}"]
    if threads_cursor:
        command += ["-F", f"threadsCursor={threads_cursor}"]
    return run_json(command, stdin=GRAPHQL_QUERY)


def fetch_pull_request(owner: str, repo: str, number: int) -> dict[str, Any]:
    top_level_comments: list[dict[str, Any]] = []
    reviews: list[dict[str, Any]] = []
    review_threads: list[dict[str, Any]] = []
    seen_comment_ids: set[str] = set()
    seen_review_ids: set[str] = set()
    seen_thread_ids: set[str] = set()

    comments_cursor: str | None = None
    reviews_cursor: str | None = None
    threads_cursor: str | None = None
    fetch_comments = True
    fetch_reviews = True
    fetch_threads = True
    pr_meta: dict[str, Any] | None = None

    while fetch_comments or fetch_reviews or fetch_threads:
        payload = graphql_fetch(
            owner=owner,
            repo=repo,
            number=number,
            fetch_comments=fetch_comments,
            fetch_reviews=fetch_reviews,
            fetch_threads=fetch_threads,
            comments_cursor=comments_cursor,
            reviews_cursor=reviews_cursor,
            threads_cursor=threads_cursor,
        )

        if "errors" in payload and payload["errors"]:
            raise RuntimeError(json.dumps(payload["errors"], indent=2))

        pr = payload["data"]["repository"]["pullRequest"]
        if pr_meta is None:
            pr_meta = {
                "number": pr["number"],
                "title": pr["title"],
                "url": pr["url"],
                "state": pr["state"],
                "owner": owner,
                "repo": repo,
            }

        if fetch_comments:
            comments_connection = pr["comments"]
            for comment in comments_connection["nodes"] or []:
                comment_id = comment.get("id")
                if comment_id and comment_id in seen_comment_ids:
                    continue
                if comment_id:
                    seen_comment_ids.add(comment_id)
                top_level_comments.append(comment)
            fetch_comments = comments_connection["pageInfo"]["hasNextPage"]
            comments_cursor = (
                comments_connection["pageInfo"]["endCursor"] if fetch_comments else None
            )

        if fetch_reviews:
            reviews_connection = pr["reviews"]
            for review in reviews_connection["nodes"] or []:
                review_id = review.get("id")
                if review_id and review_id in seen_review_ids:
                    continue
                if review_id:
                    seen_review_ids.add(review_id)
                reviews.append(review)
            fetch_reviews = reviews_connection["pageInfo"]["hasNextPage"]
            reviews_cursor = (
                reviews_connection["pageInfo"]["endCursor"] if fetch_reviews else None
            )

        if fetch_threads:
            threads_connection = pr["reviewThreads"]
            for thread in threads_connection["nodes"] or []:
                thread_id = thread.get("id")
                if thread_id and thread_id in seen_thread_ids:
                    continue
                if thread_id:
                    seen_thread_ids.add(thread_id)
                review_threads.append(thread)
            fetch_threads = threads_connection["pageInfo"]["hasNextPage"]
            threads_cursor = threads_connection["pageInfo"]["endCursor"] if fetch_threads else None

    if pr_meta is None:
        raise RuntimeError("Failed to load pull request metadata")

    return {
        "pull_request": pr_meta,
        "comments": top_level_comments,
        "reviews": reviews,
        "review_threads": review_threads,
    }


def slugify(text: str) -> str:
    normalized = text.lower()
    normalized = re.sub(r"[^a-z0-9]+", "-", normalized)
    normalized = normalized.strip("-")
    return normalized or "review-item"


def parse_review_item_thread_id(path: Path) -> str | None:
    content = path.read_text(encoding="utf-8")
    top_section = content.split(f"\n{REVIEW_ITEM_TOP_SECTION_END}\n", 1)[0]

    for line in top_section.splitlines():
        if not line.startswith("Thread ID:"):
            continue
        _, value = line.split(":", 1)
        thread_id = value.strip()
        if thread_id:
            return thread_id

    return None


def discover_existing_thread_files(pr_dir: Path) -> dict[str, Path]:
    existing: dict[str, Path] = {}
    fallback_pattern = re.compile(r"--(?P<thread_id>.+)\.md$")
    for status in ("todo", "done", "ignored"):
        directory = pr_dir / status
        if not directory.exists():
            continue
        for path in directory.glob("*.md"):
            thread_id = parse_review_item_thread_id(path)
            if not thread_id:
                match = fallback_pattern.search(path.name)
                thread_id = match.group("thread_id") if match else None
            if thread_id:
                existing[thread_id] = path
    return existing


def render_thread_file(
    *,
    index: int,
    pr: dict[str, Any],
    thread: dict[str, Any],
    thread_texts: list[str],
    title: str,
) -> str:
    comments = thread["comments"]["nodes"] or []
    primary_comment = comments[0] if comments else None
    primary_comment_database_id = (
        str(primary_comment.get("fullDatabaseId"))
        if primary_comment and primary_comment.get("fullDatabaseId") is not None
        else "n/a"
    )
    comments_truncated_on_export = thread["comments"]["pageInfo"]["hasNextPage"]

    body_sections = []
    for comment_index, (comment, text) in enumerate(zip(comments, thread_texts, strict=True), start=1):
        comment_author = comment["author"]["login"] if comment.get("author") else "unknown"
        section = "\n".join(
            [
                f"## Comment {comment_index}",
                f"Author: {comment_author}",
                f"Created: {comment['createdAt']}",
                f"Comment URL: {comment['url']}",
                "",
                text.strip(),
            ]
        ).strip()
        body_sections.append(section)

    lines = [
        f"# Review Item {index:03d}",
        "",
        f"Title: {title}",
        f"PR: #{pr['number']} — {pr['title']}",
        f"PR URL: {pr['url']}",
        f"File: {thread.get('path') or 'n/a'}",
        f"Line: {thread.get('line') or thread.get('originalLine') or 'n/a'}",
        f"Thread ID: {thread['id']}",
        f"Primary Comment Database ID: {primary_comment_database_id}",
        f"Discussion URL: {primary_comment['url'] if primary_comment else 'n/a'}",
        f"Resolved On GitHub: {'yes' if thread['isResolved'] else 'no'}",
        f"Outdated On GitHub: {'yes' if thread['isOutdated'] else 'no'}",
        f"Thread Comments Truncated On Export: {'yes' if comments_truncated_on_export else 'no'}",
        "",
        "---",
        "",
        "\n\n".join(body_sections),
        "",
    ]
    return "\n".join(lines)


def render_walkthrough_file(comment: dict[str, Any], pr: dict[str, Any]) -> str:
    text = sanitize_comment_text(comment)
    return "\n".join(
        [
            "# CodeRabbit Walkthrough",
            "",
            f"PR: #{pr['number']} — {pr['title']}",
            f"PR URL: {pr['url']}",
            f"Author: {comment['author']['login'] if comment.get('author') else 'unknown'}",
            f"Created: {comment['createdAt']}",
            f"Comment URL: {comment['url']}",
            "",
            "---",
            "",
            text,
            "",
        ]
    )


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def ensure_out_root_scaffold(out_root: Path) -> None:
    out_root.mkdir(parents=True, exist_ok=True)

    gitignore_path = out_root / ".gitignore"
    if not gitignore_path.exists():
        write_text(gitignore_path, OUT_ROOT_GITIGNORE)
        return

    existing = gitignore_path.read_text(encoding="utf-8")
    if existing == LEGACY_OUT_ROOT_GITIGNORE:
        write_text(gitignore_path, OUT_ROOT_GITIGNORE)


def export_review_bundle(
    *,
    pr_url: str,
    out_root: Path,
    include_resolved: bool,
    strip_ai_prompts: bool,
) -> Path:
    owner, repo, number = parse_pr_url(pr_url)
    ensure_gh_authenticated()
    payload = fetch_pull_request(owner, repo, number)
    pr = payload["pull_request"]
    warnings: list[str] = []

    ensure_out_root_scaffold(out_root)

    pr_slug = slugify(pr["title"])
    pr_dir = out_root / f"pr-{pr['number']:04d}-{pr_slug}"
    context_dir = pr_dir / "context"
    todo_dir = pr_dir / "todo"
    done_dir = pr_dir / "done"
    ignored_dir = pr_dir / "ignored"

    context_dir.mkdir(parents=True, exist_ok=True)
    todo_dir.mkdir(parents=True, exist_ok=True)
    done_dir.mkdir(parents=True, exist_ok=True)
    ignored_dir.mkdir(parents=True, exist_ok=True)

    write_text(context_dir / "00-dispatch-guidance.md", DISPATCH_GUIDANCE)

    top_level_comments = payload["comments"]
    walkthrough_comment = next(
        (
            comment
            for comment in top_level_comments
            if (comment.get("author") or {}).get("login") == "coderabbitai"
            and sanitize_comment_text(comment).startswith("Walkthrough")
        ),
        None,
    )
    walkthrough_path: Path | None = None
    if walkthrough_comment:
        walkthrough_path = context_dir / "01-coderabbit-walkthrough.md"
        write_text(walkthrough_path, render_walkthrough_file(walkthrough_comment, pr))

    actionable_threads: list[dict[str, Any]] = []
    for thread in payload["review_threads"]:
        if not include_resolved and thread["isResolved"]:
            continue
        comments = thread["comments"]["nodes"] or []
        if not comments:
            continue
        actionable_threads.append(thread)

    actionable_threads.sort(
        key=lambda thread: (
            (thread["comments"]["nodes"] or [{}])[0].get("createdAt", ""),
            thread.get("path") or "",
            thread.get("line") or 0,
        )
    )

    existing_thread_files = discover_existing_thread_files(pr_dir)
    manifest_items: list[dict[str, Any]] = []

    for index, thread in enumerate(actionable_threads, start=1):
        comments = thread["comments"]["nodes"] or []
        thread_texts = [
            sanitize_comment_text(
                comment,
                strip_ai_prompts=strip_ai_prompts,
            )
            for comment in comments
        ]
        combined_text = "\n\n".join(
            sanitize_comment_text(comment, strip_ai_prompts=True, for_title=True)
            for comment in comments
        )
        title = extract_comment_title(combined_text, fallback=f"Review item {index:03d}")
        slug = slugify(title)[:80]
        filename = f"{index:03d}-{slug}--{thread['id']}.md"

        existing_path = existing_thread_files.get(thread["id"])
        if existing_path is None:
            target_directory = todo_dir
            target_path = target_directory / filename
        else:
            target_directory = existing_path.parent
            target_path = target_directory / filename
            if existing_path != target_path and existing_path.exists():
                existing_path.unlink()

        write_text(
            target_path,
            render_thread_file(
                index=index,
                pr=pr,
                thread=thread,
                thread_texts=thread_texts,
                title=title,
            ),
        )

        manifest_items.append(
            {
                "thread_id": thread["id"],
                "title": title,
                "path": thread.get("path"),
                "line": thread.get("line"),
                "status_folder": target_directory.name,
                "file": str(target_path.relative_to(pr_dir)),
                "resolved": thread["isResolved"],
                "outdated": thread["isOutdated"],
                "comments_truncated_on_export": thread["comments"]["pageInfo"]["hasNextPage"],
                "comment_count": len(comments),
                "primary_comment_node_id": comments[0]["id"],
                "primary_comment_database_id": comments[0].get("fullDatabaseId"),
                "discussion_url": comments[0]["url"],
            }
        )

        primary_comment_database_id = (
            str(comments[0].get("fullDatabaseId"))
            if comments[0].get("fullDatabaseId") is not None
            else None
        )
        if not metadata_value_present(primary_comment_database_id):
            warnings.append(
                "Warning: thread "
                f"{thread['id']} is missing a primary comment database id; "
                "the follow-up script cannot post a REST reply for it."
            )
        if thread["comments"]["pageInfo"]["hasNextPage"]:
            warnings.append(
                "Warning: thread "
                f"{thread['id']} has more than 100 comments; export truncated additional replies."
            )

    review_summaries = []
    for review in payload["reviews"]:
        text = sanitize_comment_text(review)
        first_line = text.splitlines()[0] if text else ""
        review_summaries.append(
            {
                "id": review["id"],
                "author": (review.get("author") or {}).get("login"),
                "url": review["url"],
                "first_line": first_line,
            }
        )

    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "pull_request": pr,
        "walkthrough_file": str(walkthrough_path.relative_to(pr_dir)) if walkthrough_path else None,
        "actionable_threads": manifest_items,
        "review_summaries": review_summaries,
    }
    write_text(pr_dir / "manifest.json", json.dumps(manifest, indent=2))

    index_lines = [
        f"# PR Review Bundle — #{pr['number']}",
        "",
        f"Title: {pr['title']}",
        f"PR URL: {pr['url']}",
        f"State: {pr['state']}",
        f"Generated: {manifest['generated_at']}",
        "",
        "## Context",
        "",
        f"- Dispatch guidance: `context/00-dispatch-guidance.md`",
    ]
    if walkthrough_path:
        index_lines.append("- CodeRabbit walkthrough: `context/01-coderabbit-walkthrough.md`")
    else:
        index_lines.append("- CodeRabbit walkthrough: not found")

    index_lines.extend(
        [
            "",
            "## Actionable Inline Review Threads",
            "",
            f"- Exported thread files: {len(manifest_items)}",
            f"- Review summaries intentionally not exported as action items: {len(review_summaries)}",
            "",
        ]
    )

    for item in manifest_items:
        index_lines.append(
            f"- `{item['file']}` — {item['title']} ({item['path']}:{item['line'] or 'n/a'})"
        )

    if not manifest_items:
        index_lines.append("- No actionable inline review threads matched the export filter.")

    index_lines.extend(
        [
            "",
            "## Notes",
            "",
            "- The actionable queue comes from `reviewThreads.comments`, not `reviews`.",
            "- Use the bundled follow-up script after local audit if you want to reply or resolve on GitHub.",
            "- Move files from `todo/` to `done/` or `ignored/` after audit.",
        ]
    )

    write_text(pr_dir / "README.md", "\n".join(index_lines))
    for warning in warnings:
        print(warning, file=sys.stderr)
    return pr_dir


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export clean GitHub PR review comments into local files."
    )
    parser.add_argument("pr_url", help="GitHub pull request URL")
    parser.add_argument(
        "--out-root",
        default="GitHub Reviews",
        help="Root directory for exported review bundles in the current working project (default: GitHub Reviews)",
    )
    parser.add_argument(
        "--include-resolved",
        action="store_true",
        help="Include already-resolved inline review threads in the export",
    )
    parser.add_argument(
        "--strip-ai-prompts",
        action="store_true",
        help="Remove embedded AI-agent prompt sections from exported review item bodies",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        pr_dir = export_review_bundle(
            pr_url=args.pr_url,
            out_root=Path(args.out_root),
            include_resolved=args.include_resolved,
            strip_ai_prompts=args.strip_ai_prompts,
        )
    except Exception as error:  # noqa: BLE001
        print(str(error), file=sys.stderr)
        return 1

    print(pr_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
