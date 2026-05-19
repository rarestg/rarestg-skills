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
    DEFAULT_OUT_ROOT,
    ensure_gh_authenticated,
    metadata_value_present,
    parse_pr_url,
    parse_review_item_metadata,
    post_review_reply,
    reply_url_from_response,
    resolve_review_out_root,
)

SCHEMA_VERSION = 1
QUEUE_DIR_NAME = "reply-queue"
THREAD_STATUS_FOLDERS = ("todo", "done", "ignored")
ACTIVE_DUPLICATE_STATUSES = {
    "pending",
    "posting",
    "move_pending",
    "move_failed",
    "failed",
}
POST_PENDING_STATUSES = {"pending", "failed", "move_pending", "move_failed"}
SET_FIX_PR_STATUSES = {"pending", "failed"}


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


def source_identity(draft: dict[str, Any]) -> tuple[str, str, int]:
    return (
        str(draft.get("owner") or ""),
        str(draft.get("repo") or ""),
        int(draft.get("source_pr_number") or 0),
    )


def source_identity_text(identity: tuple[str, str, int]) -> str:
    owner, repo, source_pr_number = identity
    return f"{owner}/{repo}#{source_pr_number}"


def draft_source_text(draft: dict[str, Any]) -> str:
    return source_identity_text(source_identity(draft))


def display_draft_for_summary(draft: dict[str, Any]) -> str:
    return (
        f"{draft.get('id')} "
        f"({draft.get('status')}, {draft.get('disposition')}, "
        f"{draft_source_text(draft)})"
    )


def canonical_path(path: Path) -> Path:
    return path.expanduser().resolve()


def draft_bundle_path(draft: dict[str, Any]) -> Path | None:
    source_bundle = draft.get("source_bundle")
    if source_bundle is None or not metadata_value_present(str(source_bundle)):
        return None
    return canonical_path(path_from_record(str(source_bundle)))


def draft_matches_bundle(draft: dict[str, Any], bundle: str | None) -> bool:
    if not bundle:
        return True
    draft_bundle = draft_bundle_path(draft)
    return draft_bundle is not None and draft_bundle == canonical_path(Path(bundle))


def remove_internal_fields(draft: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in draft.items() if not key.startswith("_")}


def queue_filters_are_explicit(args: argparse.Namespace) -> bool:
    return bool(
        getattr(args, "source_pr", None) is not None
        or getattr(args, "bundle", None)
        or getattr(args, "filter_draft_ids", None)
    )


def filtered_drafts(
    *,
    out_root: Path,
    status: str | None = None,
    statuses: set[str] | None = None,
    source_pr: int | None = None,
    bundle: str | None = None,
    draft_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    if draft_ids:
        seen_ids: set[str] = set()
        drafts = []
        for draft_id in draft_ids:
            draft = load_draft(out_root, draft_id)
            if draft["id"] in seen_ids:
                continue
            seen_ids.add(draft["id"])
            drafts.append(draft)
    else:
        drafts = iter_drafts(out_root)

    filtered = []
    for draft in drafts:
        draft_status = draft.get("status")
        if status and draft_status != status:
            continue
        if statuses and draft_status not in statuses:
            continue
        if source_pr is not None and int(draft.get("source_pr_number") or 0) != source_pr:
            continue
        if not draft_matches_bundle(draft, bundle):
            continue
        filtered.append(draft)
    return filtered


def source_identities(drafts: list[dict[str, Any]]) -> list[tuple[str, str, int]]:
    return sorted({source_identity(draft) for draft in drafts})


def format_source_summary(drafts: list[dict[str, Any]]) -> str:
    lines = []
    for identity in source_identities(drafts):
        source_drafts = [draft for draft in drafts if source_identity(draft) == identity]
        draft_list = ", ".join(str(draft.get("id")) for draft in source_drafts)
        lines.append(f"- {source_identity_text(identity)}: {draft_list}")
    return "\n".join(lines)


def fixed_candidates_needing_fix_pr_url(drafts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates = []
    for draft in drafts:
        if draft.get("disposition") != "fixed":
            continue
        if metadata_value_present(draft.get("fix_pr_url")):
            continue
        if draft.get("status") in {"move_pending", "move_failed"} and metadata_value_present(
            draft.get("posted_reply_url")
        ):
            continue
        candidates.append(draft)
    return candidates


def normalized_fix_pr_url(fix_pr_url: object) -> str | None:
    if fix_pr_url is None:
        return None
    text = str(fix_pr_url).strip()
    if not metadata_value_present(text):
        return None
    return text


def validate_fix_pr_url_for_draft(draft: dict[str, Any], fix_pr_url: object) -> str:
    fix_pr_url_text = normalized_fix_pr_url(fix_pr_url)
    if fix_pr_url_text is None:
        raise QueueError("Fix PR URL must not be empty.")

    try:
        fix_owner, fix_repo, _fix_number = parse_pr_url(fix_pr_url_text)
    except ValueError as error:
        raise QueueError(str(error)) from error

    if draft.get("owner") != fix_owner or draft.get("repo") != fix_repo:
        raise QueueError(
            "Fix PR URL repository does not match draft source "
            f"{draft_source_text(draft)}: {fix_pr_url_text}"
        )
    return fix_pr_url_text


def stored_fix_pr_url_for_draft(
    draft: dict[str, Any], *, require_url: bool
) -> str | None:
    if draft.get("disposition") != "fixed":
        return None

    fix_pr_url = normalized_fix_pr_url(draft.get("fix_pr_url"))
    if fix_pr_url is None:
        if require_url:
            raise QueueError(
                f"Fixed draft {draft['id']} requires a fix PR URL before posting."
            )
        return None

    return validate_fix_pr_url_for_draft(draft, fix_pr_url)


def validate_fix_pr_url_for_candidates(
    *,
    fix_pr_url: str,
    candidates: list[dict[str, Any]],
) -> None:
    errors = []
    for draft in candidates:
        try:
            validate_fix_pr_url_for_draft(draft, fix_pr_url)
        except QueueError as error:
            errors.append(str(error))
    if errors:
        raise QueueError("\n".join(sorted(set(errors))))


def validate_no_conflicting_fix_pr_urls(
    *,
    fix_pr_url: str,
    candidates: list[dict[str, Any]],
) -> None:
    fix_pr_url_text = normalized_fix_pr_url(fix_pr_url) or fix_pr_url
    conflicts = [
        draft
        for draft in candidates
        if draft.get("disposition") == "fixed"
        and metadata_value_present(draft.get("fix_pr_url"))
        and str(draft.get("fix_pr_url")).strip() != fix_pr_url_text
    ]
    if conflicts:
        raise QueueError(
            "Some fixed drafts already have a different fix PR URL:\n"
            + "\n".join(
                f"- {draft.get('id')}: {draft.get('fix_pr_url')}"
                for draft in conflicts
            )
        )


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


def draft_with_fix_pr_url(draft: dict[str, Any], fix_pr_url: object) -> dict[str, Any]:
    fix_pr_url_text = validate_fix_pr_url_for_draft(draft, fix_pr_url)
    updated = dict(draft)
    updated["fix_pr_url"] = fix_pr_url_text
    updated["reply_body"] = render_fixed_reply(
        fix_pr_url=fix_pr_url_text,
        summary=updated.get("summary") or "",
        rationale=updated.get("rationale"),
    )
    updated["last_error"] = None
    return updated


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
        "fix_pr_url": None,
        "posted_reply_url": None,
        "created_at": now,
        "updated_at": now,
        "posted_at": None,
        "last_error": None,
    }
    if disposition == "fixed" and fix_pr_url is not None:
        draft = draft_with_fix_pr_url(draft, fix_pr_url)
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
    fix_pr_url = stored_fix_pr_url_for_draft(draft, require_url=True)
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
    updated = draft_with_fix_pr_url(draft, fix_pr_url)
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


def draft_ready_for_post_preflight(
    *,
    out_root: Path,
    draft: dict[str, Any],
) -> None:
    status = draft.get("status")
    if status == "posted":
        return
    if status in {"move_pending", "move_failed"} and draft.get("posted_reply_url"):
        stored_fix_pr_url_for_draft(draft, require_url=False)
        move_review_item_after_post(out_root=out_root, draft=draft, dry_run=True)
        return
    if status == "posting":
        raise QueueError(
            f"Draft {draft['id']} is in posting state without a recorded reply URL. "
            "Inspect GitHub before retrying to avoid a duplicate reply."
        )

    reply_body_for_post(draft)
    primary_comment_database_id = draft.get("primary_comment_database_id")
    if not metadata_value_present(primary_comment_database_id):
        raise QueueError(
            f"Draft {draft['id']} is missing Primary Comment Database ID; cannot post."
        )
    move_review_item_after_post(out_root=out_root, draft=draft, dry_run=True)


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
        stored_fix_pr_url_for_draft(draft, require_url=False)
        target_path = move_review_item_after_post(
            out_root=out_root,
            draft=draft,
            dry_run=dry_run,
        )
        if dry_run:
            draft["_target_item_path"] = display_path(target_path)
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
        draft["_target_item_path"] = display_path(target_path)
        draft["_reply_body_preview"] = reply_body
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
        stored_fix_pr_url_for_draft(recovered, require_url=False)
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


def prepare_post_pending_drafts(
    *,
    out_root: Path,
    drafts: list[dict[str, Any]],
    fix_pr_url: str | None,
    explicit_scope: bool,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    if not explicit_scope and len(source_identities(drafts)) > 1:
        raise QueueError(
            "Refusing to post an unfiltered pending set that spans multiple "
            "source PRs:\n"
            f"{format_source_summary(drafts)}\n"
            "Add --source-pr <number>, --bundle <path>, or repeated "
            "--draft-id <id> to choose the intended set."
        )

    needs_fix_pr_url = fixed_candidates_needing_fix_pr_url(drafts)
    if fix_pr_url and needs_fix_pr_url and not explicit_scope:
        raise QueueError(
            "Refusing to attach a fix PR URL without an explicit scope. "
            "Add --source-pr <number>, --bundle <path>, or repeated --draft-id <id>."
        )

    if fix_pr_url:
        validate_fix_pr_url_for_candidates(
            fix_pr_url=fix_pr_url,
            candidates=needs_fix_pr_url,
        )
        validate_no_conflicting_fix_pr_urls(
            fix_pr_url=fix_pr_url,
            candidates=[draft for draft in drafts if draft.get("disposition") == "fixed"],
        )

    if needs_fix_pr_url and not fix_pr_url:
        raise QueueError(
            "Fixed drafts require a fix PR URL before posting:\n"
            + "\n".join(f"- {display_draft_for_summary(draft)}" for draft in needs_fix_pr_url)
            + "\nProvide --fix-pr-url with an explicit scope, or narrow the pending set."
        )

    prepared_for_preflight = []
    needs_fix_ids = {draft["id"] for draft in needs_fix_pr_url}
    for draft in drafts:
        working = draft
        if fix_pr_url and draft.get("id") in needs_fix_ids:
            working = set_fix_pr_url(
                out_root=out_root,
                draft=draft,
                fix_pr_url=fix_pr_url,
                dry_run=True,
            )
        draft_ready_for_post_preflight(out_root=out_root, draft=dict(working))
        prepared_for_preflight.append(working)

    if dry_run or not fix_pr_url:
        return prepared_for_preflight

    prepared = []
    for draft in prepared_for_preflight:
        if draft.get("id") in needs_fix_ids:
            draft = set_fix_pr_url(
                out_root=out_root,
                draft=draft,
                fix_pr_url=fix_pr_url,
            )
        prepared.append(draft)
    return prepared


def validate_set_fix_pr_bulk(
    *,
    candidates: list[dict[str, Any]],
    fix_pr_url: str,
    explicit_scope: bool,
) -> None:
    if candidates and not explicit_scope:
        raise QueueError(
            "Refusing to attach a fix PR URL to all pending fixed drafts without "
            "an explicit scope. Add --source-pr <number>, --bundle <path>, or "
            "repeated --draft-id <id>."
        )
    validate_fix_pr_url_for_candidates(
        fix_pr_url=fix_pr_url,
        candidates=candidates,
    )
    validate_no_conflicting_fix_pr_urls(
        fix_pr_url=fix_pr_url,
        candidates=candidates,
    )


def print_draft_result(draft: dict[str, Any], *, dry_run: bool = False) -> None:
    prefix = "[DRY RUN] " if dry_run else ""
    print(f"{prefix}Draft: {draft.get('id')}")
    print(f"  Status: {draft.get('status')}")
    print(f"  Disposition: {draft.get('disposition')}")
    print(f"  Source PR: {draft_source_text(draft)}")
    if metadata_value_present(draft.get("fix_pr_url")):
        print(f"  Fix PR URL: {draft.get('fix_pr_url')}")
    if metadata_value_present(draft.get("posted_reply_url")):
        print(f"  Posted reply URL: {draft.get('posted_reply_url')}")
    target_item_path = draft.get("_target_item_path")
    if dry_run and metadata_value_present(target_item_path):
        print(f"  Would move item to: {target_item_path}")
    elif metadata_value_present(draft.get("source_item_path")):
        print(f"  Item path: {draft.get('source_item_path')}")
    if metadata_value_present(draft.get("last_error")):
        print(f"  Last error: {draft.get('last_error')}")
    reply_body_preview = draft.get("_reply_body_preview")
    if dry_run and metadata_value_present(reply_body_preview):
        print("  Reply preview:")
        for line in str(reply_body_preview).splitlines() or [""]:
            print(f"    {line}")


def print_preview(draft: dict[str, Any], *, fix_pr_url: str | None = None) -> None:
    reply_body = None
    blocked_fixed_reply = False

    if fix_pr_url:
        if draft.get("disposition") != "fixed":
            raise QueueError("--fix-pr-url preview is only valid for fixed drafts.")
        effective_fix_pr_url = validate_fix_pr_url_for_draft(draft, fix_pr_url)
    elif draft.get("disposition") == "fixed":
        effective_fix_pr_url = stored_fix_pr_url_for_draft(draft, require_url=False)
    else:
        effective_fix_pr_url = None

    if draft.get("disposition") == "fixed":
        if effective_fix_pr_url is None:
            blocked_fixed_reply = True
        else:
            reply_body = render_fixed_reply(
                fix_pr_url=effective_fix_pr_url,
                summary=draft.get("summary") or "",
                rationale=draft.get("rationale"),
            )
    else:
        reply_body = draft.get("reply_body")
        if not metadata_value_present(reply_body) and draft.get("disposition") == "declined":
            reply_body = render_declined_reply(reason=draft.get("reason") or "")

    print(f"Draft: {draft.get('id')}")
    print(f"Status: {draft.get('status')}")
    print(f"Disposition: {draft.get('disposition')}")
    print(f"Source PR: {draft_source_text(draft)}")
    if metadata_value_present(draft.get("source_item_path")):
        print(f"Item path: {draft.get('source_item_path')}")

    if blocked_fixed_reply:
        print(
            "Reply body: intentionally blocked until a fix PR URL is attached."
        )
        print(
            "Use preview --fix-pr-url <url> to render the final reply without "
            "mutating the queue."
        )
        return

    if not metadata_value_present(reply_body):
        print("Reply body: unavailable.")
        return

    print("Reply body:")
    print(str(reply_body))


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
        out_root=resolve_review_out_root(args.out_root),
        item_path=Path(args.item),
        summary=args.summary,
        rationale=args.rationale,
        fix_pr_url=args.fix_pr_url,
    )
    print(draft["id"])
    return 0


def command_add_declined(args: argparse.Namespace) -> int:
    draft = add_declined(
        out_root=resolve_review_out_root(args.out_root),
        item_path=Path(args.item),
        reason=args.reason,
    )
    print(draft["id"])
    return 0


def command_list(args: argparse.Namespace) -> int:
    drafts = filtered_drafts(
        out_root=resolve_review_out_root(args.out_root),
        status=args.status,
        source_pr=getattr(args, "source_pr", None),
        bundle=getattr(args, "bundle", None),
        draft_ids=getattr(args, "filter_draft_ids", None),
    )
    if getattr(args, "json", False):
        print(
            json.dumps(
                [remove_internal_fields(draft) for draft in drafts],
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    for draft in drafts:
        print_draft_summary(draft)
    return 0


def command_show(args: argparse.Namespace) -> int:
    draft = load_draft(resolve_review_out_root(args.out_root), args.draft_id)
    draft.pop("_queue_path", None)
    print(json.dumps(draft, indent=2, sort_keys=True))
    return 0


def command_preview(args: argparse.Namespace) -> int:
    draft = load_draft(resolve_review_out_root(args.out_root), args.draft_id)
    print_preview(draft, fix_pr_url=args.fix_pr_url)
    return 0


def command_set_fix_pr(args: argparse.Namespace) -> int:
    out_root = resolve_review_out_root(args.out_root)
    if bool(args.draft_id) == bool(args.all_pending_fixed):
        raise QueueError("Provide exactly one of <draft-id> or --all-pending-fixed.")

    if args.all_pending_fixed:
        candidates = [
            draft
            for draft in filtered_drafts(
                out_root=out_root,
                statuses=SET_FIX_PR_STATUSES,
                source_pr=getattr(args, "source_pr", None),
                bundle=getattr(args, "bundle", None),
                draft_ids=getattr(args, "filter_draft_ids", None),
            )
            if draft.get("disposition") == "fixed"
        ]
        validate_set_fix_pr_bulk(
            candidates=candidates,
            fix_pr_url=args.fix_pr_url,
            explicit_scope=queue_filters_are_explicit(args),
        )
        for draft in candidates:
            updated = set_fix_pr_url(
                out_root=out_root,
                draft=draft,
                fix_pr_url=args.fix_pr_url,
                dry_run=args.dry_run,
            )
            print_draft_result(updated, dry_run=args.dry_run)
        if not candidates:
            print("No pending fixed drafts matched.")
        return 0

    draft = load_draft(out_root, args.draft_id)
    validate_fix_pr_url_for_candidates(
        fix_pr_url=args.fix_pr_url,
        candidates=[draft],
    )
    validate_no_conflicting_fix_pr_urls(
        fix_pr_url=args.fix_pr_url,
        candidates=[draft],
    )
    updated = set_fix_pr_url(
        out_root=out_root,
        draft=draft,
        fix_pr_url=args.fix_pr_url,
        dry_run=args.dry_run,
    )
    print_draft_result(updated, dry_run=args.dry_run)
    return 0


def command_post(args: argparse.Namespace) -> int:
    out_root = resolve_review_out_root(args.out_root)
    draft = load_draft(out_root, args.draft_id)
    posted = post_draft(out_root=out_root, draft=draft, dry_run=args.dry_run)
    print_draft_result(posted, dry_run=args.dry_run)
    return 0


def command_post_pending(args: argparse.Namespace) -> int:
    out_root = resolve_review_out_root(args.out_root)
    candidates = filtered_drafts(
        out_root=out_root,
        statuses=POST_PENDING_STATUSES,
        source_pr=getattr(args, "source_pr", None),
        bundle=getattr(args, "bundle", None),
        draft_ids=getattr(args, "filter_draft_ids", None),
    )
    prepared = prepare_post_pending_drafts(
        out_root=out_root,
        drafts=candidates,
        fix_pr_url=args.fix_pr_url,
        explicit_scope=queue_filters_are_explicit(args),
        dry_run=args.dry_run,
    )
    errors = 0
    posted_count = 0
    for draft in prepared:
        try:
            posted = post_draft(
                out_root=out_root,
                draft=draft,
                dry_run=args.dry_run,
            )
        except Exception as error:  # noqa: BLE001
            errors += 1
            print(f"{draft.get('id')}: {error}", file=sys.stderr)
            continue
        print_draft_result(posted, dry_run=args.dry_run)
        posted_count += 1

    if posted_count == 0 and errors == 0:
        print("No pending drafts matched.")
    return 1 if errors else 0


def command_recover_posting(args: argparse.Namespace) -> int:
    out_root = resolve_review_out_root(args.out_root)
    draft = load_draft(out_root, args.draft_id)
    recovered = recover_posting_draft(
        out_root=out_root,
        draft=draft,
        posted_reply_url=args.posted_reply_url,
        no_reply_posted=args.no_reply_posted,
        dry_run=args.dry_run,
    )
    print_draft_result(recovered, dry_run=args.dry_run)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Queue and post durable GitHub review-thread replies."
    )
    parser.add_argument(
        "--out-root",
        default=None,
        help=f"Root review bundle directory (default: {DEFAULT_OUT_ROOT})",
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
    list_parser.add_argument("--source-pr", type=int)
    list_parser.add_argument("--bundle")
    list_parser.add_argument("--draft-id", action="append", dest="filter_draft_ids")
    list_parser.add_argument("--json", action="store_true")
    list_parser.set_defaults(func=command_list)

    show_parser = subparsers.add_parser("show")
    show_parser.add_argument("draft_id")
    show_parser.set_defaults(func=command_show)

    preview_parser = subparsers.add_parser("preview")
    preview_parser.add_argument("draft_id")
    preview_parser.add_argument("--fix-pr-url")
    preview_parser.set_defaults(func=command_preview)

    set_fix_pr_parser = subparsers.add_parser("set-fix-pr")
    set_fix_pr_parser.add_argument("draft_id", nargs="?")
    set_fix_pr_parser.add_argument("fix_pr_url")
    set_fix_pr_parser.add_argument("--all-pending-fixed", action="store_true")
    set_fix_pr_parser.add_argument("--source-pr", type=int)
    set_fix_pr_parser.add_argument("--bundle")
    set_fix_pr_parser.add_argument("--draft-id", action="append", dest="filter_draft_ids")
    set_fix_pr_parser.add_argument("--dry-run", action="store_true")
    set_fix_pr_parser.set_defaults(func=command_set_fix_pr)

    post_parser = subparsers.add_parser("post")
    post_parser.add_argument("draft_id")
    post_parser.add_argument("--dry-run", action="store_true")
    post_parser.set_defaults(func=command_post)

    post_pending_parser = subparsers.add_parser("post-pending")
    post_pending_parser.add_argument("--fix-pr-url")
    post_pending_parser.add_argument("--source-pr", type=int)
    post_pending_parser.add_argument("--bundle")
    post_pending_parser.add_argument("--draft-id", action="append", dest="filter_draft_ids")
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
