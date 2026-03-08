#!/usr/bin/env python3
"""
Post a GitHub reply and/or resolve a review thread using an exported review item file.

This script is the mutation companion to `export_github_review_comments.py`.
It reads the reply target ids from a local review item markdown file, then uses
`gh api` to post a reply and optionally resolve the thread.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from github_review_utils import (
    ensure_gh_authenticated,
    metadata_value_present,
    parse_pr_url,
    run_json,
)

TOP_SECTION_END = "---"

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


def parse_review_item_metadata(path: Path) -> dict[str, str]:
    content = path.read_text(encoding="utf-8")
    top_section = content.split(f"\n{TOP_SECTION_END}\n", 1)[0]
    metadata: dict[str, str] = {}

    for line in top_section.splitlines():
        # only parse the top header block before the first horizontal rule
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        metadata[key.strip()] = value.strip()

    required_keys = [
        "PR URL",
        "Thread ID",
    ]
    missing = [key for key in required_keys if not metadata_value_present(metadata.get(key))]
    if missing:
        raise ValueError(
            f"Review item file is missing required metadata: {', '.join(missing)}"
        )

    return metadata


def load_reply_text(args: argparse.Namespace) -> str | None:
    if args.reply and args.reply_file:
        raise ValueError("Use either --reply or --reply-file, not both")

    if args.reply:
        return args.reply

    if args.reply_file:
        if args.reply_file == "-":
            return sys.stdin.read().strip()
        return Path(args.reply_file).read_text(encoding="utf-8").strip()

    return None


def post_reply(
    *,
    owner: str,
    repo: str,
    comment_database_id: str,
    reply_body: str,
) -> dict[str, Any]:
    return run_json(
        [
            "gh",
            "api",
            f"repos/{owner}/{repo}/pulls/comments/{comment_database_id}/replies",
            "-X",
            "POST",
            "-f",
            f"body={reply_body}",
        ]
    )


def resolve_thread(thread_id: str) -> dict[str, Any]:
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


def print_metadata(metadata: dict[str, str], *, owner: str, repo: str, number: int) -> None:
    print(f"PR: {owner}/{repo}#{number}")
    print(f"Thread ID: {metadata['Thread ID']}")
    print(f"Primary Comment Database ID: {metadata.get('Primary Comment Database ID', 'n/a')}")
    discussion_url = metadata.get("Discussion URL")
    if metadata_value_present(discussion_url):
        print(f"Discussion URL: {discussion_url}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Post a GitHub reply and/or resolve a thread from an exported review item file."
    )
    parser.add_argument("review_item", help="Path to an exported review item markdown file")
    parser.add_argument("--reply", help="Reply body to post")
    parser.add_argument(
        "--reply-file",
        help="Path to a text file containing the reply body, or '-' to read from stdin",
    )
    parser.add_argument(
        "--resolve",
        action="store_true",
        help="Resolve the GitHub review thread after posting (or as a standalone action)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the actions that would run without mutating GitHub",
    )
    parser.add_argument(
        "--show-metadata",
        action="store_true",
        help="Print parsed metadata and exit without mutating GitHub",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        review_item_path = Path(args.review_item)
        metadata = parse_review_item_metadata(review_item_path)
        owner, repo, number = parse_pr_url(metadata["PR URL"])
        reply_text = load_reply_text(args)
        primary_comment_database_id = metadata.get("Primary Comment Database ID", "n/a")

        if not args.show_metadata and reply_text is None and not args.resolve:
            raise ValueError("Nothing to do. Provide --reply/--reply-file and/or --resolve.")

        if args.show_metadata:
            print_metadata(metadata, owner=owner, repo=repo, number=number)
            return 0

        print_metadata(metadata, owner=owner, repo=repo, number=number)

        if args.dry_run:
            if reply_text is not None:
                if not metadata_value_present(primary_comment_database_id):
                    raise ValueError(
                        "Primary Comment Database ID is missing from the review item file; "
                        "cannot post a reply."
                    )
                print("\n[DRY RUN] Would post reply:")
                print(
                    "gh api "
                    f"repos/{owner}/{repo}/pulls/comments/{primary_comment_database_id}/replies "
                    "-X POST "
                    f"-f body={reply_text!r}"
                )
            if args.resolve:
                print("\n[DRY RUN] Would resolve thread:")
                print(
                    "gh api graphql -F query=@- -F "
                    f"threadId={metadata['Thread ID']!r}  # resolveReviewThread mutation"
                )
            return 0

        ensure_gh_authenticated()

        if reply_text is not None:
            if not metadata_value_present(primary_comment_database_id):
                raise ValueError(
                    "Primary Comment Database ID is missing from the review item file; "
                    "cannot post a reply."
                )
            reply_response = post_reply(
                owner=owner,
                repo=repo,
                comment_database_id=primary_comment_database_id,
                reply_body=reply_text,
            )
            print("\nReply posted:")
            print(reply_response.get("html_url") or reply_response.get("url") or reply_response)

        if args.resolve:
            resolve_response = resolve_thread(metadata["Thread ID"])
            thread = (
                resolve_response.get("data", {})
                .get("resolveReviewThread", {})
                .get("thread", {})
            )
            print("\nThread resolved:")
            print(json.dumps(thread, indent=2))

        return 0
    except Exception as error:  # noqa: BLE001
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
