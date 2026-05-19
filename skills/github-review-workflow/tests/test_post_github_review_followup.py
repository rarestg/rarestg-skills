from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import post_github_review_followup as followup  # noqa: E402


class PostGithubReviewFollowupTests(unittest.TestCase):
    def test_help_warns_stacked_cleanup_should_use_queue(self) -> None:
        help_text = followup.build_parser().format_help()
        normalized_help = " ".join(help_text.split())

        self.assertIn("For stacked PR review-comment cleanup", normalized_help)
        self.assertIn("review_reply_queue.py", normalized_help)
        self.assertIn("single-item escape hatches", normalized_help)
        self.assertIn("non-stacked local-first work", normalized_help)


if __name__ == "__main__":
    unittest.main()
