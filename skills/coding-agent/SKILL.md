---
name: coding-agent
description: >-
  Orchestrate Codex CLI and Claude Code as background assistants via tmux.
  Use when you want to delegate research, reviews, implementation, or parallel
  work to another coding agent.
allowed-tools: Bash, Read
argument-hint: '<task description>'
---

# Coding Agent

Spawn a background agent when work can be done independently. For parallel write
tasks, use separate git worktrees or directories.

## Tmux Loop

Use `remain-on-exit on` so finished output stays capturable.

```bash
tmux new-session -d -s NAME -c DIR "COMMAND" \; set remain-on-exit on
tmux capture-pane -t NAME -p -S -
tmux display-message -t NAME -p '#{pane_dead}'          # 1 means exited
tmux display-message -t NAME -p '#{pane_dead_status}'   # exit code
tmux kill-session -t NAME
```

Poll one-shot agents with:

```bash
while [ "$(tmux display-message -t NAME -p '#{pane_dead}')" != "1" ]; do sleep 1; done
```

Use descriptive session names like `codex-auth-review` or `claude-fix-78`.
Capture output before killing sessions.

## Codex CLI

Use `codex exec` for one-shot work. It requires a git repo unless
`--skip-git-repo-check` is passed.

```bash
# Review/research, no writes
tmux new-session -d -s codex-review -c ~/project \
  "codex exec --sandbox read-only 'Review auth token flow'" \; set remain-on-exit on

# Build/fix with workspace writes
tmux new-session -d -s codex-fix -c ~/project \
  "codex exec --full-auto 'Fix the failing auth tests'" \; set remain-on-exit on

# Resume the same exec thread explicitly
tmux new-session -d -s codex-followup -c ~/project \
  "codex exec resume --full-auto SESSION_ID 'Now implement the fix'" \; set remain-on-exit on
```

Useful flags: `--full-auto`, `--sandbox read-only|workspace-write|danger-full-access`,
`--yolo`, `--model`, `--json`, `-o <path>`, `--add-dir <path>`,
`--output-schema <path>`.

## Claude Code

Use `claude -p` for one-shot non-interactive runs. By default it loads normal
Claude Code context; add `--bare` for deterministic scripts that should skip
auto-discovery of CLAUDE.md, hooks, skills, plugins, MCP, and auto memory.
Bare mode also skips OAuth/keychain auth; pass explicit provider auth such as
`ANTHROPIC_API_KEY` or `apiKeyHelper`.

Prefer quoted comma lists for tools:

```bash
claude -p "Fix the bug" --allowedTools "Bash,Read,Edit"
claude -p "Review this diff" --tools "Read,Bash" --allowedTools "Read"
```

`--tools` restricts available tools. `--allowedTools` only auto-approves tool
use; it does not hide tools. For shell command scoping, use permission rules such
as `--allowedTools "Bash(git diff *),Bash(git status *),Read"`.
If Bash is disabled, provide exact file paths or enable separate search/listing
tools; `Read` alone does not list directories.

```bash
# One-shot
tmux new-session -d -s claude-review -c ~/project \
  "claude -p 'Review auth token flow'" \; set remain-on-exit on

# Deterministic scripted run
tmux new-session -d -s claude-script -c ~/project \
  "claude --bare -p 'Summarize src/auth.py' --allowedTools 'Read'" \; set remain-on-exit on

# Capture session ID for a same-thread follow-up
tmux new-session -d -s claude-thread -c ~/project \
  "claude -p 'Review auth token flow' --output-format json > /tmp/claude-thread.json" \; set remain-on-exit on
while [ "$(tmux display-message -t claude-thread -p '#{pane_dead}')" != "1" ]; do sleep 1; done
SESSION_ID=$(jq -r '.session_id' /tmp/claude-thread.json)
tmux new-session -d -s claude-thread-2 -c ~/project \
  "claude -p 'Now focus on refresh-token expiry' --resume '$SESSION_ID'" \; set remain-on-exit on
```

For parallel Claude agents, do not use `--continue`; it resumes the most recent
conversation in the current directory. Do not resume the same `SESSION_ID` in two
processes at once, because messages interleave into one transcript. Start one
session per agent, or fork first:

```bash
claude -p "Branch this thread for agent A" --resume "$SESSION_ID" --fork-session --output-format json
```

Run `--resume "$SESSION_ID"` from the same directory or a git worktree of that
repo.

Useful flags: `--output-format json|stream-json`, `--append-system-prompt`,
`--append-system-prompt-file`, `--model`, `--permission-mode acceptEdits|dontAsk`,
`--no-session-persistence`, `--add-dir <path>`.

## Rules

1. Use the agent the user asked for.
2. Keep agent prompts scoped: task, files/dirs, output path, constraints.
3. Check exit status and read output before acting on an agent result.
4. Kill tmux sessions after capturing what you need.
