---
name: export-traces-transcript
description: Use this skill when you have a Traces/Codex thread ID and need the latest durable Markdown transcript for article source material, review handoff, or later mining.
---

# Export Traces Transcript

## Purpose

Use this skill to turn a Traces/Codex thread ID into a readable Markdown
transcript.

The output should preserve the real conversation, subagent/tool instructions,
and late turns after runtime reloads, while making exact turn boundaries clear.

## Normal Use

Run the wrapper from the repo root:

```sh
node skills/export-traces-transcript/scripts/export-traces-transcript.mjs \
  019eae90-31e4-7e91-9589-60ec2c96e6d0 \
  --must-contain "REPLACE_WITH_A_PHRASE_FROM_THE_THREAD_END"
```

Use `--must-contain` for a phrase near the end of the actual conversation body,
not the trace title or metadata. It is a sanity check that the export did not
stop early.

The wrapper writes one file to `.tmp/traces/` by default:

- `<trace-id>.source.md`: rendered Markdown for reading and article mining

## Options

- `--must-contain <text>`: require text to appear in the rendered transcript's
  conversation events. Repeat this flag for multiple checks.
- `--include-tool-results`: also create `.full.md` with raw tool outputs.
- `--include-timestamps`: include timestamp attributes on turn fences.
- `--keep-json`: also keep `.source.json`, `.source.pretty.json`, and
  `traces-list.json` for debugging. With `--include-tool-results`, also keeps
  `.full.json` and `.full.pretty.json`. Kept JSON is copied immediately after
  export, so it remains available even if rendering or verification fails.
- `--out-dir <path>`: write somewhere other than `.tmp/traces`.
- `--no-reset`: skip the Traces cache reset. Use only for debugging.
- `--limit <number>` and `--max-event-chars <number>`: override the wrapper's
  conservative Traces export caps.

## What The Wrapper Does

1. Resets the local Traces cache by default.
2. Re-indexes local sessions with `traces list --json --all`.
3. Confirms the trace ID exists and prints its source path.
4. Exports Traces JSON with conversation and tool-call events.
5. Renders Markdown from JSON with explicit turn fences like `<user-turn-12>`.
6. Verifies the rendered transcript has a closing trace tag, no truncation
   marker, no capped event window, and any required `--must-contain` text.
7. Deletes intermediate JSON unless `--keep-json` was provided.

## Reading The Output

Use `.source.md` as the normal source transcript for reading and article mining.
It is rendered from JSON and wraps each real user/agent exchange in explicit
turn fences:

```md
<user-turn-12>
### User

...
</user-turn-12>

<agent-turn-12>
### Agent

...
</agent-turn-12>
```

The wrapper uses Traces JSON internally because JSON is the source of truth for
event boundaries. If you need to inspect that structure, rerun with
`--keep-json` and use `.source.json` or `.source.pretty.json`.

Rendered Markdown intentionally omits Traces event IDs and event numbers because
they are usually noise for human review. Use JSON when debugging low-level event
ordering.

Rendered Markdown also omits timestamps by default. Use `--include-timestamps`
when timing matters for debugging.

If the wrapper reports `runtime_like_skipped`, inspect the rendered Markdown and
JSON. That means a user event looked like runtime setup but had real text after
`</environment_context>`, so the renderer preserved it instead of risking
content loss.

Runtime reload markers do not always prove compaction. If you need to know
whether a reload was actual compaction, inspect the source JSONL for `compacted`
or `context_compacted` records.

User-authored content can still contain text like `### User` or `### Agent`, but
the surrounding `<user-turn-N>` / `<agent-turn-N>` fences show the real boundary.
If the boundary matters for automation, prefer JSON over Markdown.

## Lower-Level Debugging

The JSON renderer can be run directly against an existing JSON export:

```sh
node skills/export-traces-transcript/scripts/render-traces-json.mjs \
  .tmp/traces/<trace-id>.source.json \
  --output .tmp/traces/<trace-id>.source.md
```

The legacy Markdown cleaner can still be run directly against an older raw
Markdown export:

```sh
node skills/export-traces-transcript/scripts/clean-traces-markdown.mjs \
  .tmp/traces/<trace-id>.raw.md \
  --output .tmp/traces/<trace-id>.source.md
```

Use direct Traces commands only when debugging the wrapper itself. The important
implementation details are already encoded in the wrapper:

- Traces caches parsed rows in `~/.traces/traces.db`, so fresh full exports reset
  the cache first.
- `traces show` has a small default event window, so the wrapper uses a high
  `--limit`.
- `--max-event-chars` is per event, not for the whole transcript.
- `--offset` is not part of the normal flow because the renderer removes runtime
  preambles without dropping real early conversation.

## Tests

Run the self-contained skill tests with:

```sh
node --test skills/export-traces-transcript/tests/*.test.mjs
```

The default tests use fake Traces output so they are deterministic. To also run
a live smoke test against local Traces/Codex state, set:

```sh
TRACES_TEST_TRACE_ID="<trace-id>" \
TRACES_TEST_MUST_CONTAIN="<phrase from the conversation body>" \
node --test skills/export-traces-transcript/tests/*.test.mjs
```

## Final Response

Report:

- the rendered Markdown path
- any JSON paths if `--keep-json` was used
- renderer stats, especially user turns, agent turns, runtime blocks removed,
  reload markers, and skipped runtime-like blocks
- whether the required `--must-contain` text was found
- whether a full evidence export was also created
