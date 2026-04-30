#!/usr/bin/env python3
"""
Export clean GitHub PR review comments into local files under `GitHub Reviews/`
in the current working project.

The export intentionally treats inline review threads as the actionable queue,
saves CodeRabbit walkthroughs as optional context, and exports CodeRabbit
nitpick review-summary items into a separate lower-priority queue.
"""

from __future__ import annotations

import argparse
import html
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

THREAD_COMMENTS_QUERY = """\
query($threadId: ID!, $commentsCursor: String) {
  node(id: $threadId) {
    ... on PullRequestReviewThread {
      comments(first: 100, after: $commentsCursor) {
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
"""

OUT_ROOT_GITIGNORE = "*\n!.gitignore\n"
LEGACY_OUT_ROOT_GITIGNORE = "*\n!.gitignore\n!SOP.md\n"
REVIEW_ITEM_TOP_SECTION_END = "---"
WALKTHROUGH_BLOCK_PATTERN = re.compile(
    r"<!--\s*walkthrough_start\s*-->(.*?)<!--\s*walkthrough_end\s*-->",
    flags=re.S | re.I,
)
WALKTHROUGH_TRIM_AFTER_PATTERN = re.compile(
    r"(?mi)^\s*##\s+Estimated Code Review Effort\b.*$"
)
DETAILS_TAG_PATTERN = re.compile(r"</?details\b[^>]*>", flags=re.I)
DETAIL_SUMMARY_PATTERN = re.compile(
    r"<summary\b[^>]*>(.*?)</summary>",
    flags=re.S | re.I,
)
BLOCKQUOTE_WRAPPER_PATTERN = re.compile(
    r"^\s*<blockquote\b[^>]*>\s*(.*?)\s*</blockquote>\s*$",
    flags=re.S | re.I,
)
NITPICK_ITEM_START_PATTERN = re.compile(
    r"(?m)^\s*`(?P<line_range>[^`]+)`:\s*(?P<title>.+?)\s*$"
)


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


def graphql_fetch_thread_comments(
    *,
    thread_id: str,
    comments_cursor: str | None = None,
) -> dict[str, Any]:
    command = [
        "gh",
        "api",
        "graphql",
        "-F",
        "query=@-",
        "-F",
        f"threadId={thread_id}",
    ]
    if comments_cursor:
        command += ["-F", f"commentsCursor={comments_cursor}"]
    return run_json(command, stdin=THREAD_COMMENTS_QUERY)


def fetch_all_review_thread_comments(
    thread_id: str,
    initial_connection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    comments: list[dict[str, Any]] = []
    seen_comment_ids: set[str] = set()
    comments_cursor: str | None = None
    fetch_comments = True

    if initial_connection is not None:
        for comment in initial_connection["nodes"] or []:
            comment_id = comment.get("id")
            if comment_id and comment_id in seen_comment_ids:
                continue
            if comment_id:
                seen_comment_ids.add(comment_id)
            comments.append(comment)

        fetch_comments = initial_connection["pageInfo"]["hasNextPage"]
        comments_cursor = (
            initial_connection["pageInfo"]["endCursor"] if fetch_comments else None
        )

    while fetch_comments:
        if comments_cursor is None and comments:
            raise RuntimeError(
                f"Failed to continue review thread comment pagination for {thread_id}"
            )
        payload = graphql_fetch_thread_comments(
            thread_id=thread_id,
            comments_cursor=comments_cursor,
        )
        if "errors" in payload and payload["errors"]:
            raise RuntimeError(json.dumps(payload["errors"], indent=2))

        node = payload.get("data", {}).get("node")
        if node is None:
            raise RuntimeError(f"Failed to load review thread comments for {thread_id}")

        comments_connection = node["comments"]
        for comment in comments_connection["nodes"] or []:
            comment_id = comment.get("id")
            if comment_id and comment_id in seen_comment_ids:
                continue
            if comment_id:
                seen_comment_ids.add(comment_id)
            comments.append(comment)

        fetch_comments = comments_connection["pageInfo"]["hasNextPage"]
        comments_cursor = (
            comments_connection["pageInfo"]["endCursor"] if fetch_comments else None
        )

    return {
        "pageInfo": {"hasNextPage": False, "endCursor": None},
        "nodes": comments,
    }


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

    for thread in review_threads:
        comments_connection = thread.get("comments", {})
        comments_page_info = comments_connection.get("pageInfo", {})
        if comments_page_info.get("hasNextPage"):
            thread["comments"] = fetch_all_review_thread_comments(
                thread["id"],
                comments_connection,
            )

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


def parse_review_item_metadata(path: Path) -> dict[str, str]:
    content = path.read_text(encoding="utf-8")
    top_section = content.split(f"\n{REVIEW_ITEM_TOP_SECTION_END}\n", 1)[0]
    metadata: dict[str, str] = {}

    for line in top_section.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()

    return metadata


def parse_review_item_thread_id(path: Path) -> str | None:
    return parse_review_item_metadata(path).get("Thread ID") or None


def nitpick_identity(
    *,
    review_id: str,
    file_path: str,
    line_range: str,
    title: str,
) -> str:
    return "\0".join(
        [
            review_id.strip(),
            file_path.strip(),
            line_range.strip(),
            title.strip(),
        ]
    )


def nitpick_identity_from_metadata(metadata: dict[str, str]) -> str | None:
    review_id = metadata.get("Review ID")
    file_path = metadata.get("File")
    line_range = metadata.get("Line Range")
    title = metadata.get("Title")
    if not all([review_id, file_path, line_range, title]):
        return None
    return nitpick_identity(
        review_id=review_id or "",
        file_path=file_path or "",
        line_range=line_range or "",
        title=title or "",
    )


def nitpick_identity_from_item(nitpick: dict[str, Any]) -> str:
    return nitpick_identity(
        review_id=nitpick["review_id"],
        file_path=nitpick["path"],
        line_range=nitpick["line_range"] or "n/a",
        title=nitpick["title"],
    )


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


def discover_existing_nitpick_files(pr_dir: Path) -> dict[str, Path]:
    existing: dict[str, Path] = {}
    for status in ("nitpicks", "done", "ignored"):
        directory = pr_dir / status
        if not directory.exists():
            continue
        for path in directory.glob("*.md"):
            identity = nitpick_identity_from_metadata(parse_review_item_metadata(path))
            if identity:
                existing[identity] = path
    return existing


def review_item_filename(*, index: int, title: str, id_suffix: str) -> str:
    title_slug = slugify(title)[:80]
    return f"{index:03d}-{title_slug}--{id_suffix}.md"


def render_review_item_document(
    *,
    heading: str,
    pr: dict[str, Any],
    title: str,
    metadata_lines: list[str],
    body: str,
) -> str:
    lines = [
        heading,
        "",
        f"Title: {title}",
        f"PR: #{pr['number']} — {pr['title']}",
        f"PR URL: {pr['url']}",
        *metadata_lines,
        "",
        REVIEW_ITEM_TOP_SECTION_END,
        "",
        body,
        "",
    ]
    return "\n".join(lines)


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

    return render_review_item_document(
        heading=f"# Review Item {index:03d}",
        pr=pr,
        title=title,
        metadata_lines=[
            f"File: {thread.get('path') or 'n/a'}",
            f"Line: {thread.get('line') or thread.get('originalLine') or 'n/a'}",
            f"Thread ID: {thread['id']}",
            f"Primary Comment Database ID: {primary_comment_database_id}",
            f"Discussion URL: {primary_comment['url'] if primary_comment else 'n/a'}",
            f"Resolved On GitHub: {'yes' if thread['isResolved'] else 'no'}",
            f"Outdated On GitHub: {'yes' if thread['isOutdated'] else 'no'}",
            "Thread Comments Truncated On Export: "
            f"{'yes' if comments_truncated_on_export else 'no'}",
        ],
        body="\n\n".join(body_sections),
    )


def render_walkthrough_file(comment: dict[str, Any], pr: dict[str, Any]) -> str:
    text = extract_coderabbit_walkthrough_text(comment)
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


def extract_coderabbit_walkthrough_text(comment: dict[str, Any]) -> str:
    raw_body = comment.get("body") or ""
    match = WALKTHROUGH_BLOCK_PATTERN.search(raw_body)
    if match:
        text = sanitize_comment_text(
            {
                **comment,
                "body": match.group(1).strip(),
                "bodyText": None,
            }
        )
        trim_match = WALKTHROUGH_TRIM_AFTER_PATTERN.search(text)
        if trim_match:
            return text[: trim_match.start()].rstrip()
        return text
    return sanitize_comment_text(comment)


def is_coderabbit_walkthrough_comment(comment: dict[str, Any]) -> bool:
    author_login = (comment.get("author") or {}).get("login")
    if author_login != "coderabbitai":
        return False

    raw_body = comment.get("body") or ""
    if "<!-- walkthrough_start -->" in raw_body:
        return True

    text = sanitize_comment_text(comment)
    first_nonempty_line = next((line.strip() for line in text.splitlines() if line.strip()), "")
    return bool(re.match(r"^(?:#+\s*)?walkthrough\b", first_nonempty_line, flags=re.I))


def top_level_detail_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    stack_depth = 0
    block_start: int | None = None

    for match in DETAILS_TAG_PATTERN.finditer(text):
        tag = match.group(0).lower()
        if tag.startswith("</"):
            if stack_depth == 0:
                continue
            stack_depth -= 1
            if stack_depth == 0 and block_start is not None:
                blocks.append(text[block_start : match.end()])
                block_start = None
            continue

        if stack_depth == 0:
            block_start = match.start()
        stack_depth += 1

    return blocks


def parse_detail_block(block: str) -> tuple[str, str] | None:
    summary_match = DETAIL_SUMMARY_PATTERN.search(block)
    if not summary_match:
        return None

    close_index = block.lower().rfind("</details>")
    if close_index == -1:
        close_index = len(block)

    return summary_match.group(1), block[summary_match.end() : close_index]


def detail_summary_text(summary: str) -> str:
    without_tags = re.sub(r"<[^>]+>", "", summary)
    return html.unescape(re.sub(r"\s+", " ", without_tags)).strip()


def unwrap_blockquote(content: str) -> str:
    match = BLOCKQUOTE_WRAPPER_PATTERN.match(content)
    if not match:
        return content.strip()
    return match.group(1).strip()


def clean_inline_markdown(text: str) -> str:
    cleaned = detail_summary_text(text)
    wrappers = [
        (r"^`(.+)`$", r"\1"),
        (r"^\*\*(.+)\*\*$", r"\1"),
        (r"^__(.+)__$", r"\1"),
        (r"^_(.+)_$", r"\1"),
    ]

    previous = None
    while previous != cleaned:
        previous = cleaned
        for pattern, replacement in wrappers:
            cleaned = re.sub(pattern, replacement, cleaned).strip()

    return cleaned


def file_path_from_nitpick_summary(summary: str) -> str:
    match = re.match(r"^(?P<path>.+?)\s+\(\d+\)\s*$", summary)
    if match:
        return match.group("path").strip()
    return summary.strip() or "n/a"


def first_line_from_range(line_range: str) -> int | None:
    match = re.search(r"\d+", line_range)
    if not match:
        return None
    return int(match.group(0))


def extract_nitpick_items_from_file_section(
    *,
    review: dict[str, Any],
    file_path: str,
    file_body: str,
    strip_ai_prompts: bool,
) -> list[dict[str, Any]]:
    starts = list(NITPICK_ITEM_START_PATTERN.finditer(file_body))
    nitpicks: list[dict[str, Any]] = []
    author = (review.get("author") or {}).get("login") or "unknown"

    for item_index, match in enumerate(starts, start=1):
        next_start = starts[item_index].start() if item_index < len(starts) else len(file_body)
        raw_item = file_body[match.start() : next_start].strip()
        text = sanitize_comment_text(
            {
                "body": raw_item,
                "bodyText": None,
                "author": {"login": "coderabbitai"},
            },
            strip_ai_prompts=strip_ai_prompts,
        )
        if not text:
            continue

        line_range = clean_inline_markdown(match.group("line_range"))
        title = clean_inline_markdown(match.group("title"))
        nitpicks.append(
            {
                "review_id": review["id"],
                "review_url": review["url"],
                "author": author,
                "created_at": review.get("submittedAt"),
                "path": file_path,
                "line_range": line_range,
                "line": first_line_from_range(line_range),
                "title": title or f"Nitpick {item_index:03d}",
                "body": text,
            }
        )

    return nitpicks


def extract_coderabbit_nitpicks(
    review: dict[str, Any],
    *,
    strip_ai_prompts: bool,
) -> list[dict[str, Any]]:
    author_login = (review.get("author") or {}).get("login")
    if author_login != "coderabbitai":
        return []

    raw_body = review.get("body") or ""
    if "Nitpick comments" not in raw_body:
        return []

    nitpicks: list[dict[str, Any]] = []

    for block in top_level_detail_blocks(raw_body):
        parsed = parse_detail_block(block)
        if not parsed:
            continue

        summary, content = parsed
        if "nitpick comments" not in detail_summary_text(summary).lower():
            continue

        for file_block in top_level_detail_blocks(unwrap_blockquote(content)):
            file_parsed = parse_detail_block(file_block)
            if not file_parsed:
                continue

            file_summary, file_content = file_parsed
            file_path = file_path_from_nitpick_summary(detail_summary_text(file_summary))
            nitpicks.extend(
                extract_nitpick_items_from_file_section(
                    review=review,
                    file_path=file_path,
                    file_body=unwrap_blockquote(file_content),
                    strip_ai_prompts=strip_ai_prompts,
                )
            )

    return nitpicks


def render_nitpick_file(
    *,
    index: int,
    pr: dict[str, Any],
    nitpick: dict[str, Any],
) -> str:
    return render_review_item_document(
        heading=f"# Nitpick Item {index:03d}",
        pr=pr,
        title=nitpick["title"],
        metadata_lines=[
            f"File: {nitpick['path']}",
            f"Line: {nitpick['line'] or 'n/a'}",
            f"Line Range: {nitpick['line_range'] or 'n/a'}",
            f"Review ID: {nitpick['review_id']}",
            f"Review URL: {nitpick['review_url']}",
            f"Author: {nitpick['author']}",
            f"Created: {nitpick['created_at'] or 'n/a'}",
        ],
        body=nitpick["body"].strip(),
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
    nitpicks_dir = pr_dir / "nitpicks"
    done_dir = pr_dir / "done"
    ignored_dir = pr_dir / "ignored"

    context_dir.mkdir(parents=True, exist_ok=True)
    todo_dir.mkdir(parents=True, exist_ok=True)
    nitpicks_dir.mkdir(parents=True, exist_ok=True)
    done_dir.mkdir(parents=True, exist_ok=True)
    ignored_dir.mkdir(parents=True, exist_ok=True)

    top_level_comments = payload["comments"]
    walkthrough_comment = next((comment for comment in top_level_comments if is_coderabbit_walkthrough_comment(comment)), None)
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
        filename = review_item_filename(
            index=index,
            title=title,
            id_suffix=thread["id"],
        )

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
    nitpick_items: list[dict[str, Any]] = []
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
        nitpick_items.extend(
            extract_coderabbit_nitpicks(
                review,
                strip_ai_prompts=strip_ai_prompts,
            )
        )

    existing_nitpick_files = discover_existing_nitpick_files(pr_dir)
    nitpick_manifest_items: list[dict[str, Any]] = []
    for index, nitpick in enumerate(nitpick_items, start=1):
        review_id_slug = slugify(nitpick["review_id"])[:40]
        filename = review_item_filename(
            index=index,
            title=nitpick["title"],
            id_suffix=review_id_slug,
        )
        existing_path = existing_nitpick_files.get(nitpick_identity_from_item(nitpick))
        if existing_path is None:
            target_directory = nitpicks_dir
            target_path = target_directory / filename
        else:
            target_directory = existing_path.parent
            target_path = target_directory / filename
            if existing_path != target_path and existing_path.exists():
                existing_path.unlink()

        write_text(
            target_path,
            render_nitpick_file(
                index=index,
                pr=pr,
                nitpick=nitpick,
            ),
        )

        nitpick_manifest_items.append(
            {
                "review_id": nitpick["review_id"],
                "title": nitpick["title"],
                "path": nitpick["path"],
                "line": nitpick["line"],
                "line_range": nitpick["line_range"],
                "status_folder": target_directory.name,
                "file": str(target_path.relative_to(pr_dir)),
                "review_url": nitpick["review_url"],
            }
        )

    manifest = {
        "generated_at": datetime.now(UTC).isoformat(),
        "pull_request": pr,
        "walkthrough_file": str(walkthrough_path.relative_to(pr_dir)) if walkthrough_path else None,
        "actionable_threads": manifest_items,
        "nitpicks": nitpick_manifest_items,
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
            f"- Review summaries retained as metadata: {len(review_summaries)}",
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
            "## CodeRabbit Nitpicks",
            "",
            f"- Exported nitpick files: {len(nitpick_manifest_items)}",
            "",
        ]
    )

    for item in nitpick_manifest_items:
        index_lines.append(
            f"- `{item['file']}` — {item['title']} ({item['path']}:{item['line_range'] or 'n/a'})"
        )

    if not nitpick_manifest_items:
        index_lines.append("- No CodeRabbit nitpick review-summary items found.")

    index_lines.extend(
        [
            "",
            "## Notes",
            "",
            "- The actionable queue comes from `reviewThreads.comments`, not `reviews`.",
            "- CodeRabbit nitpicks come from structured `reviews` summary "
            "sections and are exported separately from actionable inline threads.",
            "- Re-running export preserves existing `todo/`, `nitpicks/`, "
            "`done/`, and `ignored/` placement for recognized items.",
            "- Existing local status files can remain on disk even when their "
            "GitHub items are not included by the current export filter.",
            "- Default workflow posts review-thread replies after local audit, "
            "but does not resolve threads, commit, push, or create PRs unless "
            "explicitly requested.",
            "- Move files from `todo/` to `done/` or `ignored/` only after "
            "local audit and the required review-thread reply.",
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
    prompt_group = parser.add_mutually_exclusive_group()
    prompt_group.add_argument(
        "--strip-ai-prompts",
        dest="strip_ai_prompts",
        action="store_true",
        default=True,
        help="Remove embedded AI-agent prompt sections from exported review item bodies (default)",
    )
    prompt_group.add_argument(
        "--include-ai-prompts",
        dest="strip_ai_prompts",
        action="store_false",
        help="Preserve embedded AI-agent prompt sections in exported review item bodies",
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
