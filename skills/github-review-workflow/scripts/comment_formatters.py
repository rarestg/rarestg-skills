from __future__ import annotations

import re
from typing import Any

NOISE_LINE_PATTERNS = [
    re.compile(r"^<!--.*-->$"),
    re.compile(r"^</?details>$"),
    re.compile(r"^Useful\? React with"),
    re.compile(r"^⚠️ .*?\| .+$"),
    re.compile(r"^_?⚠️ .*?\| .*?_?$"),
    re.compile(r"^📝 Minimal fix$"),
    re.compile(r"^Also applies to:"),
]

LEARNING_METADATA_PREFIXES = (
    "Learnt from:",
    "Repo:",
    "File:",
    "Timestamp:",
    "Learning:",
)
ANALYSIS_RESIDUE_PREFIXES = (
    "🌐 Web query:",
    "💡 Result:",
    "Citations:",
    "Repository:",
    "Length of output:",
    "### ",
    "- ",
    "* ",
    "> ",
    "http://",
    "https://",
    "`",
)
STATUS_LINE_PREFIXES = (
    "✅ ",
    "❌ ",
    "⚠️ ",
)
DETAILS_BLOCK_PATTERN = re.compile(
    r"<details>\s*<summary>(.*?)</summary>\s*(.*?)\s*</details>",
    flags=re.S | re.I,
)
DROP_DETAIL_SUMMARIES = {
    "🧩 analysis chain",
    "🧠 learnings used",
    "📝 committable suggestion",
    "🧰 tools",
}
PROMPT_DETAIL_SUMMARY = "🤖 prompt for ai agents"


def strip_markdown_wrappers(text: str) -> str:
    stripped = text.strip()
    stripped = re.sub(r"^`(.+)`$", r"\1", stripped)
    stripped = re.sub(r"^\*\*(.+)\*\*$", r"\1", stripped)
    stripped = re.sub(r"^__(.+)__$", r"\1", stripped)
    stripped = re.sub(r"^_(.+)_$", r"\1", stripped)
    return stripped.strip()


def normalize_detail_summary(text: str) -> str:
    cleaned = re.sub(r"<[^>]+>", "", text).strip()
    cleaned = strip_markdown_wrappers(cleaned)
    return cleaned.strip().lower()


def strip_coderabbit_detail_blocks(text: str, *, strip_ai_prompts: bool, for_title: bool) -> str:
    if not text or "<details>" not in text:
        return text

    def replace(match: re.Match[str]) -> str:
        summary = normalize_detail_summary(match.group(1))
        body = match.group(2).strip()

        if summary in DROP_DETAIL_SUMMARIES:
            return "\n"

        if summary == PROMPT_DETAIL_SUMMARY:
            if strip_ai_prompts or for_title:
                return "\n"
            return "\n🤖 Prompt for AI Agents\n\n" + body + "\n"

        cleaned_summary = strip_markdown_wrappers(re.sub(r"<[^>]+>", "", match.group(1)).strip())
        if cleaned_summary:
            return f"\n{cleaned_summary}\n\n{body}\n"
        return "\n" + body + "\n"

    previous = None
    output = text
    while previous != output:
        previous = output
        output = DETAILS_BLOCK_PATTERN.sub(replace, output)
    return output


def _is_learning_metadata_line(line: str) -> bool:
    return line.startswith(LEARNING_METADATA_PREFIXES)


def _is_status_line(line: str) -> bool:
    return line.startswith(STATUS_LINE_PREFIXES)


def _is_analysis_chain_residue(line: str) -> bool:
    return line.startswith(ANALYSIS_RESIDUE_PREFIXES) or bool(re.match(r"^\d+:\s+https?://", line))


def _consume_script_block(lines: list[str], start_index: int) -> int:
    index = start_index + 1
    while index < len(lines):
        stripped = lines[index].strip()
        index += 1
        if stripped.startswith("Length of output:"):
            break

    while index < len(lines) and (not lines[index].strip() or lines[index].strip() == "---"):
        index += 1

    return index


def _consume_learnings_block(lines: list[str], start_index: int) -> int:
    index = start_index + 1
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped:
            next_index = index + 1
            while next_index < len(lines) and not lines[next_index].strip():
                next_index += 1
            if next_index < len(lines) and not _is_learning_metadata_line(
                lines[next_index].strip()
            ):
                return next_index
            index = next_index
            continue

        if _is_learning_metadata_line(stripped):
            index += 1
            continue

        return index

    return index


def _consume_ai_prompt_block(lines: list[str], start_index: int) -> int:
    index = start_index + 1
    while index < len(lines):
        stripped = lines[index].strip()
        if _is_status_line(stripped) or stripped == "🧠 Learnings used":
            return index

        if not stripped:
            next_index = index + 1
            while next_index < len(lines) and not lines[next_index].strip():
                next_index += 1
            if next_index < len(lines) and (
                _is_status_line(lines[next_index].strip())
                or lines[next_index].strip() == "🧠 Learnings used"
            ):
                return next_index
            index = next_index
            continue

        index += 1

    return index


def _consume_analysis_chain(lines: list[str], start_index: int) -> int:
    index = start_index + 1
    while index < len(lines):
        stripped = lines[index].strip()
        if not stripped or stripped == "---":
            index += 1
            continue

        if stripped == "🏁 Script executed:":
            index = _consume_script_block(lines, index)
            continue

        if stripped == "🧠 Learnings used":
            index = _consume_learnings_block(lines, index)
            continue

        if _is_analysis_chain_residue(stripped):
            index += 1
            continue

        break

    return index


def _strip_noise_blocks(lines: list[str], *, strip_ai_prompts: bool, for_title: bool) -> list[str]:
    filtered: list[str] = []
    index = 0

    while index < len(lines):
        stripped = lines[index].strip()

        if stripped == "🧩 Analysis chain":
            index = _consume_analysis_chain(lines, index)
            continue

        if stripped == "🏁 Script executed:":
            index = _consume_script_block(lines, index)
            continue

        if stripped == "🧠 Learnings used":
            index = _consume_learnings_block(lines, index)
            continue

        if stripped == "🤖 Prompt for AI Agents" and (strip_ai_prompts or for_title):
            index = _consume_ai_prompt_block(lines, index)
            continue

        if (
            strip_ai_prompts or for_title
        ) and stripped == "Verify each finding against the current code and only fix it if needed.":
            index += 1
            continue

        filtered.append(lines[index])
        index += 1

    return filtered


def sanitize_visible_text(
    text: str, *, strip_ai_prompts: bool = False, for_title: bool = False
) -> str:
    if not text:
        return ""

    lines: list[str] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue

        if any(pattern.match(stripped) for pattern in NOISE_LINE_PATTERNS):
            continue

        if stripped.startswith("<summary>") and stripped.endswith("</summary>"):
            inner = re.sub(r"^<summary>|</summary>$", "", stripped)
            inner = inner.strip()
            if inner:
                lines.append(inner)
            continue

        if re.fullmatch(r"<[^>]+>", stripped):
            continue

        lines.append(line)

    output = "\n".join(lines)
    output = re.sub(
        r"\n📝 Committable suggestion\n.*?(?=\n(?:🧰 Tools|🤖 Prompt for AI Agents)\n|\Z)",
        "\n",
        output,
        flags=re.S,
    )
    output = re.sub(
        r"\n🧰 Tools\n.*?(?=\n🤖 Prompt for AI Agents\n|\Z)",
        "\n",
        output,
        flags=re.S,
    )
    output = re.sub(r"\n```suggestion\n(?:\n)*", "\n", output)
    output_lines = output.splitlines()
    output_lines = _strip_noise_blocks(
        output_lines,
        strip_ai_prompts=strip_ai_prompts,
        for_title=for_title,
    )
    output = "\n".join(output_lines)
    output = re.sub(r"^(?:---\n+)+", "", output)
    output = re.sub(r"\n+(?:---\n*)+$", "", output)
    output = re.sub(r"\n{3,}", "\n\n", output)
    return output.strip()


def sanitize_generic_comment(
    comment: dict[str, Any], *, strip_ai_prompts: bool = False, for_title: bool = False
) -> str:
    source_text = comment.get("bodyText") or comment.get("body") or ""
    return sanitize_visible_text(
        source_text,
        strip_ai_prompts=strip_ai_prompts,
        for_title=for_title,
    )


def sanitize_coderabbit_comment(
    comment: dict[str, Any], *, strip_ai_prompts: bool = False, for_title: bool = False
) -> str:
    raw_body = comment.get("body") or ""
    if raw_body:
        prepared_text = strip_coderabbit_detail_blocks(
            raw_body,
            strip_ai_prompts=strip_ai_prompts,
            for_title=for_title,
        )
        return sanitize_visible_text(
            prepared_text,
            strip_ai_prompts=strip_ai_prompts,
            for_title=for_title,
        )

    return sanitize_generic_comment(
        comment,
        strip_ai_prompts=strip_ai_prompts,
        for_title=for_title,
    )


def sanitize_comment_text(
    comment: dict[str, Any], *, strip_ai_prompts: bool = False, for_title: bool = False
) -> str:
    author_login = (comment.get("author") or {}).get("login")
    if author_login == "coderabbitai":
        return sanitize_coderabbit_comment(
            comment,
            strip_ai_prompts=strip_ai_prompts,
            for_title=for_title,
        )
    return sanitize_generic_comment(
        comment,
        strip_ai_prompts=strip_ai_prompts,
        for_title=for_title,
    )


def extract_comment_title(text: str, fallback: str) -> str:
    for raw_line in text.splitlines():
        line = strip_markdown_wrappers(raw_line)
        if not line:
            continue
        normalized = line.lower()
        if "potential issue" in normalized:
            continue
        if normalized.endswith("severity"):
            continue
        if normalized.startswith("medium severity"):
            continue
        if normalized.startswith("low severity"):
            continue
        if normalized.startswith("high severity"):
            continue
        if normalized.startswith("bugbot autofix"):
            continue
        if normalized.startswith("🧩 analysis chain"):
            continue
        if normalized.startswith("also applies to:"):
            continue
        if normalized.startswith("🤖 prompt for ai agents"):
            continue
        return line
    return fallback
