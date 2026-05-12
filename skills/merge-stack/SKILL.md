---
name: merge-stack
description: >-
  Merge a linear stack of GitHub PRs into main one by one. Use when the user
  has multiple PRs that form a chain and wants to merge them sequentially.
  Triggers on phrases like "merge the stack", "merge my PRs", or "merge
  stacked PRs".
disable-model-invocation: true
allowed-tools: Bash, Read, Glob, Grep
argument-hint: "[branch-prefix]"
---

# Merge Stacked PRs

Merge a linear chain of stacked PRs into `main` one at a time, re-targeting
each subsequent PR to `main` before merging.

## Workflow

### 1. Discover the stack

```bash
gh pr list --state open \
  --json number,title,headRefName,baseRefName,additions,deletions \
  --jq '.[] | "#\(.number) \(.headRefName) → \(.baseRefName) (+\(.additions) -\(.deletions))"'
```

If a branch prefix argument is provided, filter to only PRs whose branch names
match it. Confirm the PRs form a single linear chain ending at `main`. Show the
user the full stack, bottom to top, and get confirmation before proceeding.

### 2. Merge bottom-up

Starting with the PR that targets `main`:

1. Merge it: `gh pr merge <number> --merge`
2. For each next PR in the chain:
   a. Inspect its current base. If GitHub already re-targeted it to `main`,
      continue. Otherwise, re-target it to `main` with the REST API:

      ```bash
      repo=$(gh repo view --json nameWithOwner --jq .nameWithOwner)
      gh api -X PATCH "repos/${repo}/pulls/<number>" -f base=main \
        --jq '"#\(.number) \(.head.ref) → \(.base.ref)"'
      ```

      If `GH_HOST` is set to a host that is not the PR host, unset or correct
      it for both commands. For a GitHub.com PR from an environment with a stale
      enterprise/internal `GH_HOST`, use:

      ```bash
      repo=$(env -u GH_HOST gh repo view --json nameWithOwner --jq .nameWithOwner)
      env -u GH_HOST gh api -X PATCH "repos/${repo}/pulls/<number>" -f base=main \
        --jq '"#\(.number) \(.head.ref) → \(.base.ref)"'
      ```

   b. Merge it: `gh pr merge <number> --merge`
3. Repeat until all PRs are merged.

Use `--merge`, not `--squash` or `--rebase`, to preserve commit history unless
the user requests otherwise.

Do not pass `--delete-branch` to `gh pr merge` for stacked PRs. If the repo is
configured to delete merged branches, let GitHub do that server-side. A local
CLI-driven branch deletion can remove the base branch before GitHub re-targets
dependent PRs, causing the next PR in the stack to close instead of retargeting
to `main`.

Prefer the REST retarget command above instead of
`gh pr edit <number> --base main`. GitHub CLI 2.45.0 can route `gh pr edit`
through a broader GraphQL path that queries `repository.pullRequest.projectCards`
even when no project flag is used. That can fail because Projects Classic fields
are deprecated. The REST "Update a pull request" endpoint accepts `base`
directly and changes exactly the field this workflow needs.

If REST retargeting fails, stop and report the GitHub error. Do not fall back
to `gh pr edit`; permission, validation, and base-branch errors should be fixed
directly. Fine-grained tokens need pull-request write access.

Changing a PR base can make commits disappear from the PR timeline and mark
review comments outdated. This workflow still does it intentionally because each
PR is merged into `main` first, then the next PR must target the newly updated
base. Retargeting does not update or merge `main` into the PR head branch.

References:

- <https://github.com/cli/cli/issues/11983>
- <https://github.com/cli/cli/issues/11986>
- <https://docs.github.com/en/graphql/overview/breaking-changes>
- <https://docs.github.com/en/rest/pulls/pulls#update-a-pull-request>
- [Changing the base branch of a pull request][change-base]

[change-base]: https://docs.github.com/en/pull-requests/collaborating-with-pull-requests/proposing-changes-to-your-work-with-pull-requests/changing-the-base-branch-of-a-pull-request

### 3. Verify

```bash
gh pr list --state open
```

Confirm zero open PRs remain (or only unrelated PRs remain) and report the result.

## Notes

- Always show the user the discovered stack and get confirmation before merging anything.
- If a merge fails (e.g. conflicts), stop and report the issue rather than continuing.
- If a merge fails because required CI checks have not passed, common after
  re-targeting to `main`, suggest `gh pr merge <number> --merge --auto` to
  auto-merge once checks pass.
- The branch naming pattern is typically incremental, for example `feature-1`,
  `feature-2`, but detect the actual chain by following base branch references,
  not by name pattern.
