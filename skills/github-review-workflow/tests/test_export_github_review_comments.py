from __future__ import annotations

import sys
import unittest
from pathlib import Path


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from export_github_review_comments import (  # noqa: E402
    extract_coderabbit_nitpicks,
    extract_coderabbit_outside_diff_comments,
    extract_nitpick_items_from_file_section,
    legacy_nitpick_identity_from_item,
    nitpick_identity_from_item,
    nitpick_identity_from_metadata,
    parse_blockquoted_nitpick_file_sections,
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
<details><summary>Review NITPICK comments (1)</summary>
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

    def test_extracts_outside_diff_range_comments(self) -> None:
        body = """
> [!CAUTION]
> Some comments are outside the diff and can't be posted inline.
>
> <details>
> <summary>⚠️ Outside diff range comments (1)</summary><blockquote>
>
> <details>
> <summary>skills/example.py (1)</summary><blockquote>
>
> `12-13`: _⚠️ Potential issue_ | _🟠 Major_
>
> **Keep identity stable.**
>
> Use a canonical body hash.
>
> </blockquote></details>
>
> </blockquote></details>
"""

        comments = extract_coderabbit_outside_diff_comments(
            coderabbit_review(body),
            strip_ai_prompts=True,
        )

        self.assertEqual(1, len(comments))
        self.assertEqual("Outside Diff Range", comments[0]["review_summary_type"])
        self.assertEqual("skills/example.py", comments[0]["path"])
        self.assertEqual("12-13", comments[0]["line_range"])

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

    def test_blockquoted_file_group_fallback_ignores_non_file_details(self) -> None:
        body = """
<details><summary>Nitpick comments (1)</summary>

> skills/example.py (1)
>
> `12-13`: **Prefer explicit checks**
>
> Use the explicit value.
>
> <details>
> <summary>Suggested fix</summary>
>
> ```diff
> - old
> + new
> ```
>
> </details>
</details>
"""

        nitpicks = extract_coderabbit_nitpicks(
            coderabbit_review(body),
            strip_ai_prompts=True,
        )

        self.assertEqual(1, len(nitpicks))
        self.assertEqual("skills/example.py", nitpicks[0]["path"])
        self.assertEqual("Prefer explicit checks", nitpicks[0]["title"])

    def test_blockquoted_file_group_parser_preserves_nested_quotes(self) -> None:
        sections = parse_blockquoted_nitpick_file_sections(
            """
> skills/example.py (1)
>
> `12-13`: **Prefer explicit checks**
>
> > Keep this nested quote marker.
"""
        )

        self.assertEqual(1, len(sections))
        self.assertIn("> Keep this nested quote marker.", sections[0][1])

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

    def test_body_hash_is_independent_of_ai_prompt_export_flag(self) -> None:
        file_body = """
`10`: **Same title**

Visible body.

<details>
<summary>🤖 Prompt for AI Agents</summary>

```
Use this private prompt.
```

</details>
"""

        stripped_items = extract_nitpick_items_from_file_section(
            review=coderabbit_review(""),
            file_path="skills/example.py",
            file_body=file_body,
            strip_ai_prompts=True,
        )
        included_items = extract_nitpick_items_from_file_section(
            review=coderabbit_review(""),
            file_path="skills/example.py",
            file_body=file_body,
            strip_ai_prompts=False,
        )

        self.assertEqual(1, len(stripped_items))
        self.assertEqual(1, len(included_items))
        self.assertNotEqual(stripped_items[0]["body"], included_items[0]["body"])
        self.assertEqual(stripped_items[0]["body_hash"], included_items[0]["body_hash"])

    def test_status_line_title_uses_body_title(self) -> None:
        comments = extract_nitpick_items_from_file_section(
            review=coderabbit_review(""),
            file_path="skills/example.py",
            file_body="""
`10`: _⚠️ Potential issue_ | _🟠 Major_ | _⚡ Quick win_

**Keep identity stable.**

Visible body.
""",
            strip_ai_prompts=True,
        )

        self.assertEqual(1, len(comments))
        self.assertEqual("Keep identity stable.", comments[0]["title"])


if __name__ == "__main__":
    unittest.main()
