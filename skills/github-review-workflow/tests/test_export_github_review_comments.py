from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from export_github_review_comments import (  # noqa: E402
    extract_coderabbit_nitpicks,
    extract_nitpick_items_from_file_section,
    legacy_nitpick_identity_from_item,
    nitpick_identity_from_item,
    nitpick_identity_from_metadata,
)


def coderabbit_review(body: str) -> dict:
    return {
        "id": "PRR_test",
        "url": "https://github.com/example/repo/pull/1#pullrequestreview-1",
        "submittedAt": "2026-04-30T00:00:00Z",
        "author": {"login": "coderabbitai"},
        "body": body,
    }


class ExportGithubReviewCommentsTests(unittest.TestCase):
    def test_extracts_case_insensitive_combined_nitpick_heading(self) -> None:
        body = """
<details><summary>Outside diff range and nitpick comments (1)</summary>
<blockquote>
<details><summary>skills/example.py (1)</summary>
`12-13`: **Prefer explicit checks**

Use the explicit value.
</details>
</blockquote>
</details>
"""

        nitpicks = extract_coderabbit_nitpicks(
            coderabbit_review(body),
            strip_ai_prompts=True,
        )

        self.assertEqual(1, len(nitpicks))
        self.assertEqual("skills/example.py", nitpicks[0]["path"])
        self.assertEqual("12-13", nitpicks[0]["line_range"])

    def test_extracts_markdown_blockquoted_file_groups(self) -> None:
        body = """
<details><summary>Nitpick comments (2)</summary>

> skills/example.py (2)
>
> `12-13`: **Prefer explicit checks**
>
> Use the explicit value.
>
> `20`: **Reuse helper**
>
> Avoid duplicating the parsing logic.
</details>
"""

        nitpicks = extract_coderabbit_nitpicks(
            coderabbit_review(body),
            strip_ai_prompts=True,
        )

        self.assertEqual(2, len(nitpicks))
        self.assertEqual(
            ["skills/example.py", "skills/example.py"],
            [item["path"] for item in nitpicks],
        )
        self.assertEqual(["12-13", "20"], [item["line_range"] for item in nitpicks])

    def test_body_hash_disambiguates_matching_nitpick_titles(self) -> None:
        nitpicks = extract_nitpick_items_from_file_section(
            review=coderabbit_review(""),
            file_path="skills/example.py",
            file_body="""
`10`: **Same title**

First body.

`10`: **Same title**

Second body.
""",
            strip_ai_prompts=True,
        )

        self.assertEqual(2, len(nitpicks))
        self.assertEqual(
            legacy_nitpick_identity_from_item(nitpicks[0]),
            legacy_nitpick_identity_from_item(nitpicks[1]),
        )
        self.assertNotEqual(
            nitpick_identity_from_item(nitpicks[0]),
            nitpick_identity_from_item(nitpicks[1]),
        )
        self.assertEqual(
            nitpick_identity_from_item(nitpicks[0]),
            nitpick_identity_from_metadata(
                {
                    "Review ID": nitpicks[0]["review_id"],
                    "File": nitpicks[0]["path"],
                    "Line Range": nitpicks[0]["line_range"],
                    "Title": nitpicks[0]["title"],
                    "Body Hash": nitpicks[0]["body_hash"],
                }
            ),
        )


if __name__ == "__main__":
    unittest.main()
