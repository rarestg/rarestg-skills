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

from github_review_utils import (
    ensure_gh_authenticated,
    metadata_value_present,
    parse_pr_url,
    parse_review_item_metadata,
    post_review_reply,
    reply_url_from_response,
    resolve_review_thread,
    resolved_thread_from_response,
)


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
        metadata = parse_review_item_metadata(
            review_item_path,
            required_keys=("PR URL", "Thread ID"),
        )
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
                    f"repos/{owner}/{repo}/pulls/{number}/comments/"
                    f"{primary_comment_database_id}/replies "
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

        reply_posted = False

        if reply_text is not None:
            if not metadata_value_present(primary_comment_database_id):
                raise ValueError(
                    "Primary Comment Database ID is missing from the review item file; "
                    "cannot post a reply."
                )
            reply_response = post_review_reply(
                owner=owner,
                repo=repo,
                pull_number=number,
                comment_database_id=primary_comment_database_id,
                reply_body=reply_text,
            )
            print("\nReply posted:")
            print(reply_url_from_response(reply_response) or reply_response)
            reply_posted = True

        if args.resolve:
            try:
                resolve_response = resolve_review_thread(metadata["Thread ID"])
                thread = resolved_thread_from_response(resolve_response)
            except Exception as error:
                if reply_posted:
                    raise RuntimeError(
                        f"{error}\n\n"
                        "Reply was posted, but resolving the thread failed. "
                        "Do not post a duplicate reply; rerun this script with "
                        "`--resolve` only after fixing the GitHub/auth issue."
                    ) from error
                raise
            print("\nThread resolved:")
            print(json.dumps(thread, indent=2))

        return 0
    except Exception as error:  # noqa: BLE001
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
