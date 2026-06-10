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
        self.out_root = self.root / queue.DEFAULT_OUT_ROOT
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

    def make_review_item(
        self,
        *,
        pr_number: int,
        thread_id: str,
        database_id: str,
    ) -> Path:
        bundle = self.out_root / f"pr-{pr_number:04d}-example-pr"
        todo_dir = bundle / "todo"
        todo_dir.mkdir(parents=True, exist_ok=True)
        (bundle / "done").mkdir(exist_ok=True)
        (bundle / "ignored").mkdir(exist_ok=True)
        item = todo_dir / f"001-prefer-helper--{thread_id}.md"
        item.write_text(
            review_item_text(
                pr_number=pr_number,
                thread_id=thread_id,
                database_id=database_id,
            ),
            encoding="utf-8",
        )
        return item

    def run_queue_command(self, *argv: str) -> int:
        parser = queue.build_parser()
        args = parser.parse_args(["--out-root", str(self.out_root), *argv])
        return args.func(args)

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

    def test_posted_draft_does_not_block_new_cycle_or_get_overwritten(self) -> None:
        draft = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
            fix_pr_url="https://github.com/example/repo/pull/6",
        )
        draft["status"] = "posted"
        draft["posted_reply_url"] = "https://github.com/example/repo/pull/2#reply"
        queue.save_draft(self.out_root, draft)

        next_draft = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Handle the follow-up request.",
            fix_pr_url="https://github.com/example/repo/pull/7",
        )

        self.assertNotEqual(draft["id"], next_draft["id"])
        saved_old = self.load_draft_json(draft["id"])
        saved_new = self.load_draft_json(next_draft["id"])
        self.assertEqual("posted", saved_old["status"])
        self.assertEqual("pending", saved_new["status"])
        self.assertEqual(
            "https://github.com/example/repo/pull/2#reply",
            saved_old["posted_reply_url"],
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

    def test_add_fixed_rejects_wrong_repo_fix_pr_url_before_saving(self) -> None:
        with self.assertRaisesRegex(queue.QueueError, "does not match"):
            queue.add_fixed(
                out_root=self.out_root,
                item_path=self.item,
                summary="Use the shared helper.",
                fix_pr_url="https://github.com/other/repo/pull/6",
            )

        self.assertFalse((self.out_root / "reply-queue").exists())

    def test_add_fixed_rejects_invalid_fix_pr_url_before_saving(self) -> None:
        with self.assertRaisesRegex(queue.QueueError, "Expected a GitHub pull request URL"):
            queue.add_fixed(
                out_root=self.out_root,
                item_path=self.item,
                summary="Use the shared helper.",
                fix_pr_url="not-a-pr-url",
            )

        self.assertFalse((self.out_root / "reply-queue").exists())

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

    def test_set_fix_pr_rejects_wrong_repo_url(self) -> None:
        draft = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
        )

        with self.assertRaisesRegex(queue.QueueError, "does not match"):
            self.run_queue_command(
                "set-fix-pr",
                draft["id"],
                "https://github.com/other/repo/pull/6",
            )

        self.assertIsNone(self.load_draft_json(draft["id"])["fix_pr_url"])

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

    def test_dry_run_post_rejects_stored_wrong_repo_fix_pr_url(self) -> None:
        draft = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
            fix_pr_url="https://github.com/example/repo/pull/6",
        )
        draft["fix_pr_url"] = "https://github.com/other/repo/pull/6"
        draft["reply_body"] = (
            "Addressed in https://github.com/other/repo/pull/6: Use the shared helper."
        )
        queue.save_draft(self.out_root, draft)

        with patch.object(queue, "post_review_reply") as post_reply:
            with self.assertRaisesRegex(queue.QueueError, "does not match"):
                queue.post_draft(
                    out_root=self.out_root,
                    draft=queue.load_draft(self.out_root, draft["id"]),
                    dry_run=True,
                )

        post_reply.assert_not_called()
        self.assertTrue(self.item.exists())
        self.assertEqual("pending", self.load_draft_json(draft["id"])["status"])

    def test_dry_run_post_rerenders_stale_fixed_reply_body(self) -> None:
        draft = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
            fix_pr_url="https://github.com/example/repo/pull/6",
        )
        draft["reply_body"] = (
            "Addressed in https://github.com/other/repo/pull/6: Use the shared helper."
        )
        queue.save_draft(self.out_root, draft)

        posted = queue.post_draft(
            out_root=self.out_root,
            draft=queue.load_draft(self.out_root, draft["id"]),
            dry_run=True,
        )

        self.assertIn(
            "Addressed in https://github.com/example/repo/pull/6: Use the shared helper.",
            posted["_reply_body_preview"],
        )
        self.assertNotIn("other/repo", posted["_reply_body_preview"])
        self.assertTrue(self.item.exists())
        self.assertEqual("pending", self.load_draft_json(draft["id"])["status"])

    def test_move_pending_rejects_stored_wrong_repo_fix_pr_url(self) -> None:
        draft = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
            fix_pr_url="https://github.com/example/repo/pull/6",
        )
        draft["status"] = "move_pending"
        draft["posted_reply_url"] = "https://github.com/example/repo/pull/2#reply"
        draft["fix_pr_url"] = "https://github.com/other/repo/pull/6"
        queue.save_draft(self.out_root, draft)

        with patch.object(queue, "post_review_reply") as post_reply:
            with self.assertRaisesRegex(queue.QueueError, "does not match"):
                queue.post_draft(
                    out_root=self.out_root,
                    draft=queue.load_draft(self.out_root, draft["id"]),
                    dry_run=True,
                )

        post_reply.assert_not_called()
        self.assertTrue(self.item.exists())
        self.assertFalse((self.done_dir / self.item.name).exists())

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

    def test_recover_posting_with_verified_reply_url_moves_without_reposting(self) -> None:
        draft = queue.add_declined(
            out_root=self.out_root,
            item_path=self.item,
            reason="The existing behavior is intentional.",
        )
        draft["status"] = "posting"
        draft["last_error"] = "Missing reply URL."
        queue.save_draft(self.out_root, draft)

        with patch.object(queue, "post_review_reply") as post_reply:
            recovered = queue.recover_posting_draft(
                out_root=self.out_root,
                draft=queue.load_draft(self.out_root, draft["id"]),
                posted_reply_url="https://github.com/example/repo/pull/2#reply",
            )

        post_reply.assert_not_called()
        self.assertEqual("posted", recovered["status"])
        self.assertEqual(
            "https://github.com/example/repo/pull/2#reply",
            recovered["posted_reply_url"],
        )
        self.assertFalse(self.item.exists())
        self.assertTrue((self.ignored_dir / self.item.name).exists())
        saved = self.load_draft_json(draft["id"])
        self.assertEqual("posted", saved["status"])
        self.assertIsNone(saved["last_error"])

    def test_recover_posting_without_reply_marks_failed_for_retry(self) -> None:
        draft = queue.add_declined(
            out_root=self.out_root,
            item_path=self.item,
            reason="The existing behavior is intentional.",
        )
        draft["status"] = "posting"
        draft["last_error"] = "Missing reply URL."
        queue.save_draft(self.out_root, draft)

        recovered = queue.recover_posting_draft(
            out_root=self.out_root,
            draft=queue.load_draft(self.out_root, draft["id"]),
            no_reply_posted=True,
        )

        self.assertEqual("failed", recovered["status"])
        self.assertIn("no reply was posted", recovered["last_error"])
        self.assertTrue(self.item.exists())
        saved = self.load_draft_json(draft["id"])
        self.assertEqual("failed", saved["status"])

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

    def test_list_filters_by_source_pr_bundle_and_draft_id(self) -> None:
        draft_2 = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
        )
        item_3 = self.make_review_item(
            pr_number=3,
            thread_id="THREAD_3",
            database_id="33333",
        )
        draft_3 = queue.add_declined(
            out_root=self.out_root,
            item_path=item_3,
            reason="Out of scope.",
        )

        output = StringIO()
        with redirect_stdout(output):
            self.run_queue_command("list", "--source-pr", "2")
        self.assertIn(draft_2["id"], output.getvalue())
        self.assertNotIn(draft_3["id"], output.getvalue())

        output = StringIO()
        with redirect_stdout(output):
            self.run_queue_command("list", "--bundle", str(item_3.parent.parent))
        self.assertNotIn(draft_2["id"], output.getvalue())
        self.assertIn(draft_3["id"], output.getvalue())

        output = StringIO()
        with redirect_stdout(output):
            self.run_queue_command("list", "--draft-id", draft_2["id"])
        self.assertIn(draft_2["id"], output.getvalue())
        self.assertNotIn(draft_3["id"], output.getvalue())

    def test_post_pending_unfiltered_multi_source_fails_before_mutation(self) -> None:
        draft_2 = queue.add_declined(
            out_root=self.out_root,
            item_path=self.item,
            reason="The existing behavior is intentional.",
        )
        item_3 = self.make_review_item(
            pr_number=3,
            thread_id="THREAD_3",
            database_id="33333",
        )
        draft_3 = queue.add_declined(
            out_root=self.out_root,
            item_path=item_3,
            reason="Out of scope.",
        )

        with patch.object(queue, "post_review_reply") as post_reply:
            with self.assertRaisesRegex(queue.QueueError, "multiple source PRs"):
                self.run_queue_command("post-pending")

        post_reply.assert_not_called()
        self.assertEqual("pending", self.load_draft_json(draft_2["id"])["status"])
        self.assertEqual("pending", self.load_draft_json(draft_3["id"])["status"])
        self.assertTrue(self.item.exists())
        self.assertTrue(item_3.exists())

    def test_post_pending_scoped_fix_url_only_updates_matching_drafts(self) -> None:
        draft_2 = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
        )
        item_3 = self.make_review_item(
            pr_number=3,
            thread_id="THREAD_3",
            database_id="33333",
        )
        draft_3 = queue.add_fixed(
            out_root=self.out_root,
            item_path=item_3,
            summary="Use the other helper.",
        )

        with (
            patch.object(queue, "ensure_gh_authenticated"),
            patch.object(
                queue,
                "post_review_reply",
                return_value={"html_url": "https://github.com/example/repo/pull/2#reply"},
            ) as post_reply,
            redirect_stdout(StringIO()),
        ):
            self.run_queue_command(
                "post-pending",
                "--source-pr",
                "2",
                "--fix-pr-url",
                "https://github.com/example/repo/pull/6",
            )

        post_reply.assert_called_once()
        saved_2 = self.load_draft_json(draft_2["id"])
        saved_3 = self.load_draft_json(draft_3["id"])
        self.assertEqual("posted", saved_2["status"])
        self.assertEqual("https://github.com/example/repo/pull/6", saved_2["fix_pr_url"])
        self.assertEqual("pending", saved_3["status"])
        self.assertIsNone(saved_3["fix_pr_url"])
        self.assertFalse(self.item.exists())
        self.assertTrue(item_3.exists())

    def test_post_pending_fix_url_repo_mismatch_fails_before_mutation(self) -> None:
        draft = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
        )

        with patch.object(queue, "post_review_reply") as post_reply:
            with self.assertRaisesRegex(queue.QueueError, "does not match"):
                self.run_queue_command(
                    "post-pending",
                    "--source-pr",
                    "2",
                    "--fix-pr-url",
                    "https://github.com/other/repo/pull/6",
                )

        post_reply.assert_not_called()
        saved = self.load_draft_json(draft["id"])
        self.assertEqual("pending", saved["status"])
        self.assertIsNone(saved["fix_pr_url"])

    def test_set_fix_pr_all_pending_fixed_requires_explicit_scope(self) -> None:
        draft = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
        )

        with self.assertRaisesRegex(queue.QueueError, "explicit scope"):
            self.run_queue_command(
                "set-fix-pr",
                "--all-pending-fixed",
                "https://github.com/example/repo/pull/6",
            )

        self.assertIsNone(self.load_draft_json(draft["id"])["fix_pr_url"])

    def test_set_fix_pr_all_pending_fixed_rejects_conflicting_url(self) -> None:
        draft = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
            fix_pr_url="https://github.com/example/repo/pull/6",
        )

        with self.assertRaisesRegex(queue.QueueError, "different fix PR URL"):
            self.run_queue_command(
                "set-fix-pr",
                "--all-pending-fixed",
                "--source-pr",
                "2",
                "https://github.com/example/repo/pull/7",
            )

        self.assertEqual(
            "https://github.com/example/repo/pull/6",
            self.load_draft_json(draft["id"])["fix_pr_url"],
        )

    def test_command_post_prints_detailed_result(self) -> None:
        draft = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
            fix_pr_url="https://github.com/example/repo/pull/6",
        )

        output = StringIO()
        with (
            patch.object(queue, "ensure_gh_authenticated"),
            patch.object(
                queue,
                "post_review_reply",
                return_value={"html_url": "https://github.com/example/repo/pull/2#reply"},
            ),
            redirect_stdout(output),
        ):
            self.run_queue_command("post", draft["id"])

        result = output.getvalue()
        self.assertIn(f"Draft: {draft['id']}", result)
        self.assertIn("Status: posted", result)
        self.assertIn("Disposition: fixed", result)
        self.assertIn("Source PR: example/repo#2", result)
        self.assertIn("Fix PR URL: https://github.com/example/repo/pull/6", result)
        self.assertIn("Posted reply URL: https://github.com/example/repo/pull/2#reply", result)
        self.assertIn("Item path:", result)

    def test_preview_explains_blocked_fixed_reply_and_renders_with_url(self) -> None:
        draft = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
            rationale="This avoids duplicate parsing.",
        )

        output = StringIO()
        with redirect_stdout(output):
            self.run_queue_command("preview", draft["id"])
        self.assertIn("intentionally blocked", output.getvalue())

        output = StringIO()
        with redirect_stdout(output):
            self.run_queue_command(
                "preview",
                draft["id"],
                "--fix-pr-url",
                "https://github.com/example/repo/pull/6",
            )
        preview = output.getvalue()
        self.assertIn(
            "Addressed in https://github.com/example/repo/pull/6: Use the shared helper.",
            preview,
        )
        self.assertIn("This avoids duplicate parsing.", preview)

    def test_preview_rejects_wrong_repo_fix_pr_url(self) -> None:
        draft = queue.add_fixed(
            out_root=self.out_root,
            item_path=self.item,
            summary="Use the shared helper.",
        )

        with self.assertRaisesRegex(queue.QueueError, "does not match"):
            self.run_queue_command(
                "preview",
                draft["id"],
                "--fix-pr-url",
                "https://github.com/other/repo/pull/6",
            )


if __name__ == "__main__":
    unittest.main()
