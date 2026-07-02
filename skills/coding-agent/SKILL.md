---
name: coding-agent
description: >-
  Delegate, consult, or review with Codex CLI and Claude Code for research,
  planning, implementation, or parallel coding-agent work.
---

# Coding Agent

Spawn another coding agent when work can be done independently. For parallel
write tasks, use separate git worktrees or directories.

Use the CLIs directly. Capture output to files when you need durable handoff or
thread IDs, and check exit status before acting on the result.

## Codex CLI

Use `codex exec` directly. It requires `jq` when capturing a thread ID from
JSON. In externally sandboxed agent environments, use full-access mode so Codex
does not stall on sandbox or approval prompts:
`--dangerously-bypass-approvals-and-sandbox`, or `--yolo` on CLIs that support
that shorthand. Add `--skip-git-repo-check` to every call when running outside a
git repository.

```bash
set -euo pipefail
RUN_DIR=$(mktemp -d "${TMPDIR:-/tmp}/codex.XXXXXX")
codex exec --dangerously-bypass-approvals-and-sandbox --json \
  -o "$RUN_DIR/final.txt" - > "$RUN_DIR/events.jsonl" <<'PROMPT'
<prompt>
PROMPT
THREAD_ID=$(jq -r 'select(.type=="thread.started") | .thread_id' "$RUN_DIR/events.jsonl" | tail -1)
test -n "$THREAD_ID" || { echo "No thread.started event; inspect $RUN_DIR/events.jsonl" >&2; exit 1; }

# Resume the same thread by explicit ID.
codex exec --dangerously-bypass-approvals-and-sandbox --json \
  -o "$RUN_DIR/final-2.txt" resume "$THREAD_ID" - > "$RUN_DIR/events-2.jsonl" <<'PROMPT'
<next prompt>
PROMPT
```

Put global flags such as `--dangerously-bypass-approvals-and-sandbox`,
`--json`, `--sandbox`, `-o`, and `--skip-git-repo-check` before the `resume`
subcommand. `-` reads prompts from stdin for both initial and resumed turns;
`-o` writes the final assistant message while `--json` streams JSONL to stdout.

Never use `codex exec resume --last` or `resume --all` for agent orchestration.
They are ambiguous when multiple agents or directories are active. Always
resume by explicit `THREAD_ID`.

Useful flags: `--model`, `--add-dir <path>`, `--output-schema <path>`.
`--yolo` is a shorthand alias for
`--dangerously-bypass-approvals-and-sandbox` on CLIs that support it.

## Review Touchpoints

Use the lightest loop that fits the task:

1. Pre-plan brainstorm: for complex or high-stakes work, before writing a plan,
   give the other agent the problem, your current thinking, and what you would
   put in the plan. Ask for challenges, missing risks, simpler paths, or reasons
   no change is needed.
2. Plan review: after the plan is written and before implementation, have the
   other agent review the plan from first principles.
3. Change review: after changes are made and before final handoff, have the
   other agent review the diff or changed files.

For plan and change reviews, provide:

- the goal and trigger for the work;
- relevant code, architecture, files, or diff;
- the proposed path, framed as context rather than a conclusion;
- an explicit request to challenge assumptions, inherited requirements,
  complexity, failure modes, and hidden coupling.

Tell the other agent to ask 1-3 material questions before its final answer, or
to say there are none and proceed. Answer questions in the same thread/session,
then use the verdict as input to your own judgment. "Plan is solid", "a smaller
change is enough", and "no change needed" are valid outcomes.

When fanning work out to other agents, have each agent use this same review
loop, but only for the last two touchpoints: plan review and change review. The
orchestrator keeps the pre-plan brainstorm.

Each agent should open its own Codex thread or Claude session for plan review,
then reuse that same thread/session for change review. Do not share one
thread/session across parallel agents.

## Claude Code

Use `claude -p` for one-shot non-interactive runs. By default it loads normal
Claude Code context; add `--bare` for deterministic scripts that should skip
auto-discovery of CLAUDE.md, hooks, skill/plugin discovery, and auto memory.
Explicit flags and `/skill-name` still work.
Bare mode also skips OAuth/keychain auth; pass explicit provider auth such as
`ANTHROPIC_API_KEY` or `apiKeyHelper`.

Use `--permission-mode auto` for autonomous CLI runs. In non-interactive `-p`
runs, repeated auto-mode blocks can abort because there is no approval prompt to
fall back to.

Prefer quoted comma lists for tools:

```bash
claude --permission-mode auto -p "Fix the bug" --allowedTools "Bash,Read,Edit"
claude --permission-mode auto -p "Review this diff" --tools "Read,Bash" --allowedTools "Read"
```

`--tools` restricts available tools. `--allowedTools` only auto-approves tool
use; it does not hide tools. For shell command scoping, use permission rules such
as `--allowedTools "Bash(git diff *),Bash(git status *),Read"`.
If Bash is disabled, provide exact file paths or enable separate search/listing
tools; `Read` alone does not list directories. With auto mode, prefer narrow
permission rules; broad blanket allow rules may not behave like blanket
approvals.

```bash
set -euo pipefail
RUN_DIR=$(mktemp -d "${TMPDIR:-/tmp}/claude.XXXXXX")

# One-shot
claude --permission-mode auto -p "Review auth token flow" > "$RUN_DIR/review.out"

# Deterministic scripted run
claude --permission-mode auto --bare -p "Summarize src/auth.py" \
  --allowedTools "Read" > "$RUN_DIR/script.out"

# Capture session ID for a same-thread follow-up
claude --permission-mode auto -p "Review auth token flow" \
  --output-format json > "$RUN_DIR/thread.json"
SESSION_ID=$(jq -r '.session_id' "$RUN_DIR/thread.json")
test -n "$SESSION_ID" || { echo "No session_id; inspect $RUN_DIR/thread.json" >&2; exit 1; }
claude --permission-mode auto -p "Now focus on refresh-token expiry" \
  --resume "$SESSION_ID" > "$RUN_DIR/thread-2.out"
```

`--bare` changes discovery and auth behavior, not permission mode.

For parallel Claude agents, do not use `--continue`; it resumes the most recent
conversation in the current directory. Do not resume the same `SESSION_ID` in two
processes at once, because messages interleave into one transcript. Start one
session per agent, or fork first:

```bash
claude --permission-mode auto -p "Branch this thread for agent A" \
  --resume "$SESSION_ID" --fork-session --output-format json > "$RUN_DIR/fork-a.json"
FORK_SESSION_ID=$(jq -r '.session_id' "$RUN_DIR/fork-a.json")
test -n "$FORK_SESSION_ID" || { echo "No session_id; inspect $RUN_DIR/fork-a.json" >&2; exit 1; }
```

Run `--resume "$SESSION_ID"` from the same directory or a git worktree of that
repo.

Useful flags: `--output-format json|stream-json`, `--append-system-prompt`,
`--append-system-prompt-file`, `--model`,
`--permission-mode default|acceptEdits|plan|auto|dontAsk|bypassPermissions`,
`--no-session-persistence`, `--add-dir <path>`.

## Rules

1. Use the agent the user asked for.
2. Keep agent prompts scoped: task, files or directories, output path,
   constraints.
3. Check exit status and read output before acting on an agent result.
4. For Codex, keep one thread per task or delegated agent and resume by explicit
   thread ID.
