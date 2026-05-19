#!/usr/bin/env python3
"""
Maintain a durable local queue of GitHub review-thread replies.

The queue is intentionally narrow: it records reply drafts for exported
thread-backed review items, posts those replies when they are accurate, and
moves the local review item only after posting succeeds.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from github_review_utils import (
    ensure_gh_authenticated,
    metadata_value_present,
    parse_pr_url,
    parse_review_item_metadata,
    post_review_reply,
    reply_url_from_response,
)

SCHEMA_VERSION = 1
DEFAULT_OUT_ROOT = Path("GitHub Reviews")
QUEUE_DIR_NAME = "reply-queue"
THREAD_STATUS_FOLDERS = ("todo", "done", "ignored")
ACTIVE_DUPLICATE_STATUSES = {
    "pending",
    "posting",
    "move_pending",
    "move_failed",
    "failed",
}


class QueueError(Exception):
    """Raised for expected queue workflow failures."""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


def queue_dir(out_root: Path) -> Path:
    return out_root / QUEUE_DIR_NAME


def queue_path(out_root: Path, draft_id: str) -> Path:
    return queue_dir(out_root) / f"{draft_id}.json"


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temp_path.replace(path)


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(Path.cwd().resolve()))
    except ValueError:
        return str(path.resolve())


def path_from_record(path_text: str) -> Path:
    path = Path(path_text)
    if path.is_absolute():
        return path
    return Path.cwd() / path


def review_item_type(metadata: dict[str, str]) -> str:
    if metadata_value_present(metadata.get("Thread ID")):
        return "thread"
    if metadata_value_present(metadata.get("Review Summary Type")):
        return "outside-diff"
    if metadata_value_present(metadata.get("Review ID")):
        return "review-summary"
    return "unknown"


def source_bundle_for_item(item_path: Path) -> Path:
    if item_path.parent.name in {"todo", "done", "ignored", "outside-diff", "nitpicks"}:
        return item_path.parent.parent
    raise QueueError(
        f"Review item path is not inside a known bundle status folder: {item_path}"
    )


def draft_id_for(
    *,
    owner: str,
    repo: str,
    source_pr_number: int,
    thread_id: str,
    disposition: str,
) -> str:
    digest = hashlib.sha256(
        "\0".join(
            [
                owner,
                repo,
                str(source_pr_number),
                thread_id,
                disposition,
            ]
        ).encode("utf-8")
    ).hexdigest()[:16]
    return f"pr{source_pr_number}-{disposition}-{digest}"


def next_available_draft_id(out_root: Path, base_draft_id: str) -> str:
    if not queue_path(out_root, base_draft_id).exists():
        return base_draft_id

    cycle = 2
    while queue_path(out_root, f"{base_draft_id}-{cycle}").exists():
        cycle += 1
    return f"{base_draft_id}-{cycle}"


def render_fixed_reply(
    *,
    fix_pr_url: str,
    summary: str,
    rationale: str | None = None,
) -> str:
    reply = f"Addressed in {fix_pr_url}: {summary.strip()}"
    if rationale and rationale.strip():
        reply = f"{reply}\n\n{rationale.strip()}"
    return reply


def render_declined_reply(*, reason: str) -> str:
    return f"Not taking this change: {reason.strip()}"


def iter_draft_paths(out_root: Path) -> list[Path]:
    directory = queue_dir(out_root)
    if not directory.exists():
        return []
    return sorted(directory.glob("*.json"))


def iter_drafts(out_root: Path) -> list[dict[str, Any]]:
    drafts = []
    for path in iter_draft_paths(out_root):
        draft = read_json(path)
        draft["_queue_path"] = str(path)
        drafts.append(draft)
    return drafts


def find_duplicate_draft(
    *,
    out_root: Path,
    owner: str,
    repo: str,
    source_pr_number: int,
    thread_id: str,
    disposition: str,
) -> dict[str, Any] | None:
    for draft in iter_drafts(out_root):
        if draft.get("status") not in ACTIVE_DUPLICATE_STATUSES:
            continue
        if (
            draft.get("owner") == owner
            and draft.get("repo") == repo
            and draft.get("source_pr_number") == source_pr_number
            and draft.get("thread_id") == thread_id
            and draft.get("disposition") == disposition
        ):
            return draft
    return None


def load_draft(out_root: Path, draft_id: str) -> dict[str, Any]:
    exact_path = queue_path(out_root, draft_id)
    if exact_path.exists():
        draft = read_json(exact_path)
        draft["_queue_path"] = str(exact_path)
        return draft

    matches = [path for path in iter_draft_paths(out_root) if path.stem.startswith(draft_id)]
    if len(matches) == 1:
        draft = read_json(matches[0])
        draft["_queue_path"] = str(matches[0])
        return draft
    if matches:
        raise QueueError(f"Draft id prefix is ambiguous: {draft_id}")
    raise QueueError(f"Draft not found: {draft_id}")


def save_draft(out_root: Path, draft: dict[str, Any]) -> None:
    payload = {key: value for key, value in draft.items() if not key.startswith("_")}
    payload["updated_at"] = utc_now()
    atomic_write_json(queue_path(out_root, payload["id"]), payload)


def build_base_draft(
    *,
    out_root: Path,
    item_path: Path,
    disposition: str,
    target_folder: str,
    summary: str | None = None,
    rationale: str | None = None,
    reason: str | None = None,
    fix_pr_url: str | None = None,
) -> dict[str, Any]:
    metadata = parse_review_item_metadata(
        item_path,
        required_keys=("PR URL", "Thread ID"),
    )
    item_type = review_item_type(metadata)
    if item_type != "thread":
        raise QueueError(
            "Only thread-backed review item files can be queued for per-thread replies."
        )

    owner, repo, source_pr_number = parse_pr_url(metadata["PR URL"])
    thread_id = metadata["Thread ID"]
    existing = find_duplicate_draft(
        out_root=out_root,
        owner=owner,
        repo=repo,
        source_pr_number=source_pr_number,
        thread_id=thread_id,
        disposition=disposition,
    )
    if existing:
        raise QueueError(
            "A draft already exists for this thread and disposition: "
            f"{existing.get('id')} ({existing.get('status')})"
        )

    now = utc_now()
    base_draft_id = draft_id_for(
        owner=owner,
        repo=repo,
        source_pr_number=source_pr_number,
        thread_id=thread_id,
        disposition=disposition,
    )
    draft_id = next_available_draft_id(out_root, base_draft_id)
    primary_comment_database_id = metadata.get("Primary Comment Database ID")
    discussion_url = metadata.get("Discussion URL")
    draft = {
        "schema_version": SCHEMA_VERSION,
        "id": draft_id,
        "status": "pending",
        "disposition": disposition,
        "owner": owner,
        "repo": repo,
        "source_pr_number": source_pr_number,
        "source_pr_url": metadata["PR URL"],
        "item_type": item_type,
        "thread_id": thread_id,
        "primary_comment_database_id": primary_comment_database_id,
        "discussion_url": discussion_url,
        "source_bundle": display_path(source_bundle_for_item(item_path)),
        "source_item_path": display_path(item_path),
        "target_folder": target_folder,
        "summary": summary,
        "rationale": rationale,
        "reason": reason,
        "reply_body": None,
        "fix_pr_url": fix_pr_url,
        "posted_reply_url": None,
        "created_at": now,
        "updated_at": now,
        "posted_at": None,
        "last_error": None,
    }
    if disposition == "fixed" and fix_pr_url:
        draft["reply_body"] = render_fixed_reply(
            fix_pr_url=fix_pr_url,
            summary=summary or "",
            rationale=rationale,
        )
    elif disposition == "declined":
        draft["reply_body"] = render_declined_reply(reason=reason or "")
    return draft


def add_fixed(
    *,
    out_root: Path,
    item_path: Path,
    summary: str,
    rationale: str | None = None,
    fix_pr_url: str | None = None,
) -> dict[str, Any]:
    if not summary.strip():
        raise QueueError("--summary must not be empty")
    draft = build_base_draft(
        out_root=out_root,
        item_path=item_path,
        disposition="fixed",
        target_folder="done",
        summary=summary,
        rationale=rationale,
        fix_pr_url=fix_pr_url,
    )
    save_draft(out_root, draft)
    return draft


def add_declined(*, out_root: Path, item_path: Path, reason: str) -> dict[str, Any]:
    if not reason.strip():
        raise QueueError("--reason must not be empty")
    draft = build_base_draft(
        out_root=out_root,
        item_path=item_path,
        disposition="declined",
        target_folder="ignored",
        reason=reason,
    )
    save_draft(out_root, draft)
    return draft


def ensure_fixed_reply_ready(draft: dict[str, Any]) -> None:
    if draft.get("disposition") != "fixed":
        return
    fix_pr_url = draft.get("fix_pr_url")
    if not metadata_value_present(fix_pr_url):
        raise QueueError(
            f"Fixed draft {draft['id']} requires a fix PR URL before posting."
        )
    if not metadata_value_present(draft.get("reply_body")):
        draft["reply_body"] = render_fixed_reply(
            fix_pr_url=fix_pr_url,
            summary=draft.get("summary") or "",
            rationale=draft.get("rationale"),
        )


def set_fix_pr_url(
    *,
    out_root: Path,
    draft: dict[str, Any],
    fix_pr_url: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    if draft.get("disposition") != "fixed":
        raise QueueError(f"Draft is not a fixed draft: {draft['id']}")
    updated = dict(draft)
    updated["fix_pr_url"] = fix_pr_url
    updated["reply_body"] = render_fixed_reply(
        fix_pr_url=fix_pr_url,
        summary=updated.get("summary") or "",
        rationale=updated.get("rationale"),
    )
    updated["last_error"] = None
    if not dry_run:
        save_draft(out_root, updated)
    return updated


def find_item_by_thread(draft: dict[str, Any], out_root: Path) -> Path | None:
    candidate_bundles = []
    source_bundle = draft.get("source_bundle")
    if source_bundle:
        candidate_bundles.append(path_from_record(source_bundle))
    candidate_bundles.extend(
        path for path in out_root.glob("pr-*") if path not in candidate_bundles
    )

    for bundle in candidate_bundles:
        if not bundle.exists():
            continue
        for folder in THREAD_STATUS_FOLDERS:
            directory = bundle / folder
            if not directory.exists():
                continue
            for path in sorted(directory.glob("*.md")):
                try:
                    metadata = parse_review_item_metadata(path)
                except OSError:
                    continue
                if metadata.get("Thread ID") == draft.get("thread_id"):
                    return path
    return None


def resolve_source_item_path(draft: dict[str, Any], out_root: Path) -> Path:
    source_item_path = draft.get("source_item_path")
    if source_item_path:
        candidate = path_from_record(source_item_path)
        if candidate.exists():
            return candidate

    found = find_item_by_thread(draft, out_root)
    if found:
        return found

    raise QueueError(
        f"Could not find local review item for draft {draft['id']} "
        f"(thread {draft.get('thread_id')})."
    )


def move_review_item_after_post(
    *,
    out_root: Path,
    draft: dict[str, Any],
    dry_run: bool = False,
) -> Path:
    item_path = resolve_source_item_path(draft, out_root)
    target_folder = draft.get("target_folder")
    if target_folder not in {"done", "ignored"}:
        raise QueueError(f"Invalid target folder for draft {draft['id']}: {target_folder}")

    if item_path.parent.name == target_folder:
        return item_path

    bundle = source_bundle_for_item(item_path)
    target_dir = bundle / target_folder
    target_path = target_dir / item_path.name

    if target_path.exists() and target_path.resolve() != item_path.resolve():
        raise QueueError(f"Target item already exists: {target_path}")

    if not dry_run:
        target_dir.mkdir(parents=True, exist_ok=True)
        item_path.rename(target_path)

    return target_path


def reply_body_for_post(draft: dict[str, Any]) -> str:
    ensure_fixed_reply_ready(draft)
    reply_body = draft.get("reply_body")
    if not metadata_value_present(reply_body):
        raise QueueError(f"Draft {draft['id']} has no reply body.")
    return str(reply_body)


def mark_post_failed(out_root: Path, draft: dict[str, Any], error: Exception) -> None:
    draft["status"] = "failed"
    draft["last_error"] = str(error)
    save_draft(out_root, draft)


def mark_posting_needs_inspection(out_root: Path, draft: dict[str, Any], error: Exception) -> None:
    draft["status"] = "posting"
    draft["last_error"] = str(error)
    save_draft(out_root, draft)


def mark_move_failed(out_root: Path, draft: dict[str, Any], error: Exception) -> None:
    draft["status"] = "move_failed"
    draft["last_error"] = str(error)
    save_draft(out_root, draft)


def post_draft(
    *,
    out_root: Path,
    draft: dict[str, Any],
    dry_run: bool = False,
) -> dict[str, Any]:
    status = draft.get("status")
    if status == "posted":
        return draft

    if status in {"move_pending", "move_failed"} and draft.get("posted_reply_url"):
        target_path = move_review_item_after_post(
            out_root=out_root,
            draft=draft,
            dry_run=dry_run,
        )
        if not dry_run:
            draft["status"] = "posted"
            draft["source_item_path"] = display_path(target_path)
            draft["last_error"] = None
            save_draft(out_root, draft)
        return draft

    if status == "posting":
        raise QueueError(
            f"Draft {draft['id']} is in posting state without a recorded reply URL. "
            "Inspect GitHub before retrying to avoid a duplicate reply."
        )

    reply_body = reply_body_for_post(draft)
    primary_comment_database_id = draft.get("primary_comment_database_id")
    if not metadata_value_present(primary_comment_database_id):
        raise QueueError(
            f"Draft {draft['id']} is missing Primary Comment Database ID; cannot post."
        )

    if dry_run:
        target_path = move_review_item_after_post(
            out_root=out_root,
            draft=draft,
            dry_run=True,
        )
        print(
            "[DRY RUN] Would post draft "
            f"{draft['id']} to {draft['owner']}/{draft['repo']}#{draft['source_pr_number']}"
        )
        print(reply_body)
        print(f"[DRY RUN] Would move item to {target_path}")
        return draft

    try:
        ensure_gh_authenticated()
    except Exception as error:
        mark_post_failed(out_root, draft, error)
        raise

    draft["status"] = "posting"
    draft["last_error"] = None
    save_draft(out_root, draft)

    try:
        response = post_review_reply(
            owner=draft["owner"],
            repo=draft["repo"],
            pull_number=int(draft["source_pr_number"]),
            comment_database_id=str(primary_comment_database_id),
            reply_body=reply_body,
        )
    except Exception as error:
        mark_post_failed(out_root, draft, error)
        raise

    posted_reply_url = reply_url_from_response(response)
    if not posted_reply_url:
        error = QueueError(
            "GitHub reply response did not include a reply URL. "
            "Inspect GitHub before retrying to avoid a duplicate reply."
        )
        mark_posting_needs_inspection(out_root, draft, error)
        raise error

    draft["status"] = "move_pending"
    draft["posted_reply_url"] = posted_reply_url
    draft["posted_at"] = utc_now()
    draft["last_error"] = None
    save_draft(out_root, draft)

    try:
        target_path = move_review_item_after_post(out_root=out_root, draft=draft)
    except Exception as error:
        mark_move_failed(out_root, draft, error)
        raise

    draft["status"] = "posted"
    draft["source_item_path"] = display_path(target_path)
    draft["last_error"] = None
    save_draft(out_root, draft)
    return draft


def recover_posting_draft(
    *,
    out_root: Path,
    draft: dict[str, Any],
    posted_reply_url: str | None = None,
    no_reply_posted: bool = False,
    dry_run: bool = False,
) -> dict[str, Any]:
    if draft.get("status") != "posting":
        raise QueueError(f"Draft {draft['id']} is not in posting state.")
    if bool(metadata_value_present(posted_reply_url)) == no_reply_posted:
        raise QueueError(
            "Provide exactly one posting recovery outcome: "
            "--posted-reply-url or --no-reply-posted."
        )

    recovered = dict(draft)
    recovered["last_error"] = None

    if metadata_value_present(posted_reply_url):
        recovered["status"] = "move_pending"
        recovered["posted_reply_url"] = str(posted_reply_url)
        recovered["posted_at"] = recovered.get("posted_at") or utc_now()
        if not dry_run:
            save_draft(out_root, recovered)
        return post_draft(out_root=out_root, draft=recovered, dry_run=dry_run)

    recovered["status"] = "failed"
    recovered["last_error"] = (
        "Manual inspection confirmed no reply was posted; retry is allowed."
    )
    if not dry_run:
        save_draft(out_root, recovered)
    return recovered


def print_draft_summary(draft: dict[str, Any]) -> None:
    print(
        "\t".join(
            [
                str(draft.get("id")),
                str(draft.get("status")),
                str(draft.get("disposition")),
                f"{draft.get('owner')}/{draft.get('repo')}#{draft.get('source_pr_number')}",
                str(draft.get("summary") or draft.get("reason") or ""),
            ]
        )
    )


def command_add_fixed(args: argparse.Namespace) -> int:
    draft = add_fixed(
        out_root=Path(args.out_root),
        item_path=Path(args.item),
        summary=args.summary,
        rationale=args.rationale,
        fix_pr_url=args.fix_pr_url,
    )
    print(draft["id"])
    return 0


def command_add_declined(args: argparse.Namespace) -> int:
    draft = add_declined(
        out_root=Path(args.out_root),
        item_path=Path(args.item),
        reason=args.reason,
    )
    print(draft["id"])
    return 0


def command_list(args: argparse.Namespace) -> int:
    for draft in iter_drafts(Path(args.out_root)):
        if args.status and draft.get("status") != args.status:
            continue
        print_draft_summary(draft)
    return 0


def command_show(args: argparse.Namespace) -> int:
    draft = load_draft(Path(args.out_root), args.draft_id)
    draft.pop("_queue_path", None)
    print(json.dumps(draft, indent=2, sort_keys=True))
    return 0


def command_set_fix_pr(args: argparse.Namespace) -> int:
    out_root = Path(args.out_root)
    if bool(args.draft_id) == bool(args.all_pending_fixed):
        raise QueueError("Provide exactly one of <draft-id> or --all-pending-fixed.")

    if args.all_pending_fixed:
        updated_count = 0
        for draft in iter_drafts(out_root):
            if draft.get("disposition") != "fixed":
                continue
            if draft.get("status") not in {"pending", "failed"}:
                continue
            set_fix_pr_url(
                out_root=out_root,
                draft=draft,
                fix_pr_url=args.fix_pr_url,
                dry_run=args.dry_run,
            )
            print(draft["id"])
            updated_count += 1
        if updated_count == 0:
            print("No pending fixed drafts matched.")
        return 0

    draft = load_draft(out_root, args.draft_id)
    updated = set_fix_pr_url(
        out_root=out_root,
        draft=draft,
        fix_pr_url=args.fix_pr_url,
        dry_run=args.dry_run,
    )
    print(updated["id"])
    return 0


def command_post(args: argparse.Namespace) -> int:
    out_root = Path(args.out_root)
    draft = load_draft(out_root, args.draft_id)
    posted = post_draft(out_root=out_root, draft=draft, dry_run=args.dry_run)
    print(posted["id"])
    if posted.get("posted_reply_url"):
        print(posted["posted_reply_url"])
    return 0


def command_post_pending(args: argparse.Namespace) -> int:
    out_root = Path(args.out_root)
    errors = 0
    posted_count = 0
    for draft in iter_drafts(out_root):
        if draft.get("status") not in {"pending", "failed", "move_pending", "move_failed"}:
            continue
        working = draft
        if (
            args.fix_pr_url
            and draft.get("disposition") == "fixed"
            and not metadata_value_present(draft.get("fix_pr_url"))
        ):
            working = set_fix_pr_url(
                out_root=out_root,
                draft=draft,
                fix_pr_url=args.fix_pr_url,
                dry_run=args.dry_run,
            )
        try:
            posted = post_draft(
                out_root=out_root,
                draft=working,
                dry_run=args.dry_run,
            )
        except Exception as error:  # noqa: BLE001
            errors += 1
            print(f"{draft.get('id')}: {error}", file=sys.stderr)
            continue
        print(posted["id"])
        posted_count += 1

    if posted_count == 0 and errors == 0:
        print("No pending drafts matched.")
    return 1 if errors else 0


def command_recover_posting(args: argparse.Namespace) -> int:
    out_root = Path(args.out_root)
    draft = load_draft(out_root, args.draft_id)
    recovered = recover_posting_draft(
        out_root=out_root,
        draft=draft,
        posted_reply_url=args.posted_reply_url,
        no_reply_posted=args.no_reply_posted,
        dry_run=args.dry_run,
    )
    print(recovered["id"])
    if recovered.get("posted_reply_url"):
        print(recovered["posted_reply_url"])
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Queue and post durable GitHub review-thread replies."
    )
    parser.add_argument(
        "--out-root",
        default=str(DEFAULT_OUT_ROOT),
        help="Root review bundle directory (default: GitHub Reviews)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    add_fixed_parser = subparsers.add_parser("add-fixed")
    add_fixed_parser.add_argument("item", help="Thread-backed review item file")
    add_fixed_parser.add_argument("--summary", required=True)
    add_fixed_parser.add_argument("--rationale")
    add_fixed_parser.add_argument("--fix-pr-url")
    add_fixed_parser.set_defaults(func=command_add_fixed)

    add_declined_parser = subparsers.add_parser("add-declined")
    add_declined_parser.add_argument("item", help="Thread-backed review item file")
    add_declined_parser.add_argument("--reason", required=True)
    add_declined_parser.set_defaults(func=command_add_declined)

    list_parser = subparsers.add_parser("list")
    list_parser.add_argument("--status")
    list_parser.set_defaults(func=command_list)

    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("draft_id")
    show_parser.set_defaults(func=command_show)

    set_fix_pr_parser = subparsers.add_parser("set-fix-pr")
    set_fix_pr_parser.add_argument("draft_id", nargs="?")
    set_fix_pr_parser.add_argument("fix_pr_url")
    set_fix_pr_parser.add_argument("--all-pending-fixed", action="store_true")
    set_fix_pr_parser.add_argument("--dry-run", action="store_true")
    set_fix_pr_parser.set_defaults(func=command_set_fix_pr)

    post_parser = subparsers.add_parser("post")
    post_parser.add_argument("draft_id")
    post_parser.add_argument("--dry-run", action="store_true")
    post_parser.set_defaults(func=command_post)

    post_pending_parser = subparsers.add_parser("post-pending")
    post_pending_parser.add_argument("--fix-pr-url")
    post_pending_parser.add_argument("--dry-run", action="store_true")
    post_pending_parser.set_defaults(func=command_post_pending)

    recover_posting_parser = subparsers.add_parser("recover-posting")
    recover_posting_parser.add_argument("draft_id")
    recovery_outcome = recover_posting_parser.add_mutually_exclusive_group(
        required=True
    )
    recovery_outcome.add_argument("--posted-reply-url")
    recovery_outcome.add_argument("--no-reply-posted", action="store_true")
    recover_posting_parser.add_argument("--dry-run", action="store_true")
    recover_posting_parser.set_defaults(func=command_recover_posting)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    try:
        return args.func(args)
    except Exception as error:  # noqa: BLE001
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
