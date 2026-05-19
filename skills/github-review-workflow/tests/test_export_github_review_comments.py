from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch


SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from export_github_review_comments import (  # noqa: E402
    LEGACY_OUT_ROOT_GITIGNORES,
    OUT_ROOT_GITIGNORE,
    build_bundle_manifest,
    ensure_out_root_scaffold,
    extract_coderabbit_nitpicks,
    extract_coderabbit_outside_diff_comments,
    extract_nitpick_items_from_file_section,
    legacy_nitpick_identity_from_item,
    main,
    nitpick_identity_from_item,
    nitpick_identity_from_metadata,
    parse_blockquoted_nitpick_file_sections,
    render_bundle_readme,
    render_export_summary,
)
from github_review_utils import (  # noqa: E402
    DEFAULT_OUT_ROOT,
    LEGACY_OUT_ROOT,
    STATE_SOURCE,
    resolve_review_out_root,
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
    def test_default_out_root_uses_hidden_workflow_directory(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)

            self.assertEqual(DEFAULT_OUT_ROOT, resolve_review_out_root(None, cwd=root))

    def test_legacy_out_root_guard_requires_explicit_choice(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            (root / LEGACY_OUT_ROOT).mkdir()

            with self.assertRaisesRegex(RuntimeError, "--out-root 'GitHub Reviews'"):
                resolve_review_out_root(None, cwd=root)

            self.assertEqual(
                LEGACY_OUT_ROOT,
                resolve_review_out_root(str(LEGACY_OUT_ROOT), cwd=root),
            )

            (root / DEFAULT_OUT_ROOT).mkdir()
            self.assertEqual(DEFAULT_OUT_ROOT, resolve_review_out_root(None, cwd=root))

    def test_out_root_scaffold_ignores_entire_generated_root(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            out_root = Path(temp_dir) / DEFAULT_OUT_ROOT

            ensure_out_root_scaffold(out_root)

            self.assertEqual(
                OUT_ROOT_GITIGNORE,
                (out_root / ".gitignore").read_text(encoding="utf-8"),
            )

    def test_out_root_scaffold_rewrites_legacy_gitignore_scaffolds(self) -> None:
        for legacy_gitignore in LEGACY_OUT_ROOT_GITIGNORES:
            with self.subTest(legacy_gitignore=legacy_gitignore):
                with tempfile.TemporaryDirectory() as temp_dir:
                    out_root = Path(temp_dir) / DEFAULT_OUT_ROOT
                    out_root.mkdir()
                    gitignore_path = out_root / ".gitignore"
                    gitignore_path.write_text(legacy_gitignore, encoding="utf-8")

                    ensure_out_root_scaffold(out_root)

                    self.assertEqual(
                        OUT_ROOT_GITIGNORE,
                        gitignore_path.read_text(encoding="utf-8"),
                    )

    def test_manifest_and_readme_describe_snapshot_status_model(self) -> None:
        pr = {
            "number": 7,
            "title": "Example",
            "url": "https://github.com/example/repo/pull/7",
            "state": "OPEN",
        }
        manifest = build_bundle_manifest(
            pr=pr,
            walkthrough_file=None,
            actionable_threads=[],
            outside_diff_comments=[],
            nitpicks=[],
            review_summaries=[],
        )

        readme = render_bundle_readme(
            pr=pr,
            manifest=manifest,
            has_walkthrough=False,
        )

        self.assertEqual(STATE_SOURCE, manifest["state_source"])
        self.assertIn("PR Review Bundle Snapshot", readme)
        self.assertIn("## Status Model", readme)
        self.assertIn("export snapshots", readme)
        self.assertIn("not live queue state", readme)
        self.assertIn("folder placement", readme)
        self.assertIn("../reply-queue/", readme)

    def test_render_export_summary_orients_to_included_snapshot(self) -> None:
        pr = {
            "number": 4,
            "title": "Export orientation",
            "url": "https://github.com/example/repo/pull/4",
            "state": "OPEN",
        }
        manifest = build_bundle_manifest(
            pr=pr,
            walkthrough_file="context/01-coderabbit-walkthrough.md",
            actionable_threads=[
                {"status_folder": "todo"},
                {"status_folder": "done"},
                {"status_folder": "ignored"},
            ],
            outside_diff_comments=[
                {"status_folder": "outside-diff"},
                {"status_folder": "ignored"},
            ],
            nitpicks=[
                {"status_folder": "nitpicks"},
            ],
            review_summaries=[
                {"id": "PRR_1"},
                {"id": "PRR_2"},
            ],
        )

        summary = render_export_summary(
            pr_dir=Path(".github-review-workflow/pr-0004-export-orientation"),
            manifest=manifest,
        )

        self.assertIn(
            "Export snapshot summary (included in this export; not live queue state)",
            summary,
        )
        self.assertIn("PR: #4 Export orientation", summary)
        self.assertIn(
            "Bundle: .github-review-workflow/pr-0004-export-orientation",
            summary,
        )
        self.assertIn(
            "Walkthrough: present (context/01-coderabbit-walkthrough.md)",
            summary,
        )
        self.assertIn(
            "Inline review threads: 3 included (todo 1, done 1, ignored 1)",
            summary,
        )
        self.assertIn("Outside-diff items: 2 included", summary)
        self.assertIn("Nitpicks: 1 included", summary)
        self.assertIn("Review summaries: 2 retained as metadata", summary)
        self.assertIn("- README.md", summary)
        self.assertIn("- manifest.json", summary)
        self.assertIn("- context/01-coderabbit-walkthrough.md", summary)
        self.assertIn("- todo/", summary)
        self.assertIn("- outside-diff/", summary)
        self.assertIn("- nitpicks/", summary)

    def test_main_prints_path_stdout_and_summary_stderr(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            bundle = root / ".github-review-workflow" / "pr-0009-summary"
            pr = {
                "number": 9,
                "title": "Summary contract",
                "url": "https://github.com/example/repo/pull/9",
                "state": "OPEN",
            }

            def fake_export(**kwargs: object) -> Path:
                self.assertEqual(root / ".github-review-workflow", kwargs["out_root"])
                bundle.mkdir(parents=True)
                manifest = build_bundle_manifest(
                    pr=pr,
                    walkthrough_file=None,
                    actionable_threads=[{"status_folder": "todo"}],
                    outside_diff_comments=[],
                    nitpicks=[],
                    review_summaries=[],
                )
                (bundle / "manifest.json").write_text(
                    json.dumps(manifest),
                    encoding="utf-8",
                )
                return bundle

            stdout = io.StringIO()
            stderr = io.StringIO()
            argv = [
                "export_github_review_comments.py",
                "https://github.com/example/repo/pull/9",
                "--out-root",
                str(root / ".github-review-workflow"),
            ]
            with (
                patch(
                    "export_github_review_comments.export_review_bundle",
                    side_effect=fake_export,
                ),
                patch.object(sys, "argv", argv),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = main()

            self.assertEqual(0, exit_code)
            self.assertEqual(f"{bundle}\n", stdout.getvalue())
            self.assertIn("Export snapshot summary", stderr.getvalue())
            self.assertIn(f"Bundle: {bundle}", stderr.getvalue())
            self.assertNotIn("Export snapshot summary", stdout.getvalue())

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
