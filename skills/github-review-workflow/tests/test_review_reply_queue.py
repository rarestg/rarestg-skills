from __future__ import annotations

import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import review_reply_queue as queue  # noqa: E402


def review_item_text(
    *,
    pr_number: int = 2,
    thread_id: str = "THREAD_1",
    database_id: str = "12345",
) -> str:
    return f"""# Review Item 001

Title: Prefer helper
PR: #{pr_number} - Example PR
PR URL: https://github.com/example/repo/pull/{pr_number}
File: app.py
Line: 10
Thread ID: {thread_id}
Primary Comment Database ID: {database_id}
Discussion URL: https://github.com/example/repo/pull/{pr_number}#discussion_r1
Resolved On GitHub: no
Outdated On GitHub: no
Thread Comments Truncated On Export: no

---

## Comment 1
Author: reviewer
Created: 2026-05-01T00:00:00Z
Comment URL: https://github.com/example/repo/pull/{pr_number}#discussion_r1

Use the shared helper.
"""


class ReviewReplyQueueTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.out_root = self.root / "GitHub Reviews"
        self.bundle = self.out_root / "pr-0002-example-pr"
        self.todo_dir = self.bundle / "todo"
        self.done_dir = self.bundle / "done"
        self.ignored_dir = self.bundle / "ignored"
        self.todo_dir.mkdir(parents=True)
        self.done_dir.mkdir()
        self.ignored_dir.mkdir()
        self.item = self.todo_dir / "001-prefer-helper--THREAD_1.md"
        self.item.write_text(review_item_text(), encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def load_draft_json(self, draft_id: str) -> dict:
        return json.loads((self.out_root / "reply-queue" / f"{draft_id}.json").read_text())

    def test_add_fixed_creates_pending_draft_with_stable_identity(self) -> None:
        draft = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
        )

        saved = self.load_draft_json(draft["id"])
        self.assertEqual(queue.SCHEMA_VERSION, saved["schema_version"])
        self.assertEqual("pending", saved["status"])
        self.assertEqual("fixed", saved["disposition"])
        self.assertEqual("example", saved["owner"])
        self.assertEqual("repo", saved["repo"])
        self.assertEqual(2, saved["source_pr_number"])
        self.assertEqual("THREAD_1", saved["thread_id"])
        self.assertEqual("12345", saved["primary_comment_database_id"])
        self.assertEqual("done", saved["target_folder"])
        self.assertIsNone(saved["reply_body"])

    def test_duplicate_active_draft_is_rejected(self) -> None:
        queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
        )

        with self.assertRaises(queue.QueueError):
            queue.add_fixed(
                out_root=self.out_root,
                item_path=self.item,
                summary="Use the shared helper again.",
            )

    def test_declined_draft_renders_reply_body(self) -> None:
        draft = queue.add_declined(
            out_root=self.out_root,
            item_path=self.item,
            reason="The existing behavior is intentional.",
        )

        saved = self.load_draft_json(draft["id"])
        self.assertEqual("declined", saved["disposition"])
        self.assertEqual("ignored", saved["target_folder"])
        self.assertEqual(
            "Not taking this change: The existing behavior is intentional.",
            saved["reply_body"],
        )

    def test_fixed_draft_requires_fix_pr_url_before_posting(self) -> None:
        draft = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
        )

        with self.assertRaises(queue.QueueError):
            queue.post_draft(out_root=self.out_root, draft=draft, dry_run=True)

    def test_set_fix_pr_renders_fixed_reply_body(self) -> None:
        draft = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
            rationale="This avoids duplicate parsing.",
        )

        updated = queue.set_fix_pr_url(
            out_root=self.out_root,
            draft=draft,
            fix_pr_url="https://github.com/example/repo/pull/6",
        )

        self.assertEqual(
            "Addressed in https://github.com/example/repo/pull/6: Use the shared helper.\n\n"
            "This avoids duplicate parsing.",
            updated["reply_body"],
        )

    def test_dry_run_does_not_post_or_move(self) -> None:
        draft = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
            fix_pr_url="https://github.com/example/repo/pull/6",
        )

        with (
            patch.object(queue, "post_review_reply") as post_reply,
            redirect_stdout(StringIO()),
        ):
            queue.post_draft(out_root=self.out_root, draft=draft, dry_run=True)

        post_reply.assert_not_called()
        self.assertTrue(self.item.exists())
        self.assertFalse((self.done_dir / self.item.name).exists())
        saved = self.load_draft_json(draft["id"])
        self.assertEqual("pending", saved["status"])

    def test_successful_post_records_url_and_moves_item(self) -> None:
        draft = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
            fix_pr_url="https://github.com/example/repo/pull/6",
        )

        with (
            patch.object(queue, "ensure_gh_authenticated"),
            patch.object(
                queue,
                "post_review_reply",
                return_value={"html_url": "https://github.com/example/repo/pull/2#reply"},
            ) as post_reply,
        ):
            posted = queue.post_draft(out_root=self.out_root, draft=draft)

        post_reply.assert_called_once()
        self.assertEqual("posted", posted["status"])
        self.assertFalse(self.item.exists())
        self.assertTrue((self.done_dir / self.item.name).exists())
        saved = self.load_draft_json(draft["id"])
        self.assertEqual("posted", saved["status"])
        self.assertEqual(
            "https://github.com/example/repo/pull/2#reply",
            saved["posted_reply_url"],
        )

    def test_failed_post_leaves_item_unmoved(self) -> None:
        draft = queue.add_declined(
            out_root=self.out_root,
            item_path=self.item,
            reason="The existing behavior is intentional.",
        )

        with (
            patch.object(queue, "ensure_gh_authenticated"),
            patch.object(queue, "post_review_reply", side_effect=RuntimeError("network")),
        ):
            with self.assertRaises(RuntimeError):
                queue.post_draft(out_root=self.out_root, draft=draft)

        self.assertTrue(self.item.exists())
        self.assertFalse((self.ignored_dir / self.item.name).exists())
        saved = self.load_draft_json(draft["id"])
        self.assertEqual("failed", saved["status"])
        self.assertEqual("network", saved["last_error"])

    def test_post_response_without_url_requires_manual_inspection(self) -> None:
        draft = queue.add_declined(
            out_root=self.out_root,
            item_path=self.item,
            reason="The existing behavior is intentional.",
        )

        with (
            patch.object(queue, "ensure_gh_authenticated"),
            patch.object(queue, "post_review_reply", return_value={"id": "reply-1"}),
        ):
            with self.assertRaises(queue.QueueError):
                queue.post_draft(out_root=self.out_root, draft=draft)

        self.assertTrue(self.item.exists())
        self.assertFalse((self.ignored_dir / self.item.name).exists())
        saved = self.load_draft_json(draft["id"])
        self.assertEqual("posting", saved["status"])
        self.assertIn("Inspect GitHub", saved["last_error"])

    def test_move_failure_can_recover_without_reposting(self) -> None:
        draft = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
            fix_pr_url="https://github.com/example/repo/pull/6",
        )

        with (
            patch.object(queue, "ensure_gh_authenticated"),
            patch.object(
                queue,
                "post_review_reply",
                return_value={"html_url": "https://github.com/example/repo/pull/2#reply"},
            ),
            patch.object(
                queue,
                "move_review_item_after_post",
                side_effect=queue.QueueError("move failed"),
            ),
        ):
            with self.assertRaises(queue.QueueError):
                queue.post_draft(out_root=self.out_root, draft=draft)

        failed = queue.load_draft(self.out_root, draft["id"])
        self.assertEqual("move_failed", failed["status"])
        self.assertEqual("https://github.com/example/repo/pull/2#reply", failed["posted_reply_url"])
        self.assertTrue(self.item.exists())

        with patch.object(queue, "post_review_reply") as post_reply:
            recovered = queue.post_draft(out_root=self.out_root, draft=failed)

        post_reply.assert_not_called()
        self.assertEqual("posted", recovered["status"])
        self.assertFalse(self.item.exists())
        self.assertTrue((self.done_dir / self.item.name).exists())

    def test_resolves_renamed_item_path_by_thread_id(self) -> None:
        draft = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
            fix_pr_url="https://github.com/example/repo/pull/6",
        )
        renamed = self.todo_dir / "001-renamed-title--THREAD_1.md"
        self.item.rename(renamed)

        resolved = queue.resolve_source_item_path(draft, self.out_root)

        self.assertEqual(renamed, resolved)


if __name__ == "__main__":
    unittest.main()
