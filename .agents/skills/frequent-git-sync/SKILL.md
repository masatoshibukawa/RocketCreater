---
name: frequent-git-sync
description: Keep active repository chat work synchronized with regular safe pulls, latest-PR checks, and immediate interference alerts. Require small frequent commits, immediate pushes, and current pull requests for file-changing tasks, including code, documentation, configuration, and skills.
---

# Frequent Git synchronization

The repository owner requires continuous Git synchronization during active chat work in this repository. Perform fetches, safe fast-forward pulls, and ordinary task-scoped commits, pushes, and PR creation or editing without repeatedly asking for confirmation. Commit, push, and PR obligations apply only when the task produces changes. Respect explicit user restrictions, including requests for strictly read-only work, and the environment's permission requirements.

## Required cadence

- Check incoming changes and the latest repository PR activity at task start, between work units, before committing or pushing, after pushing, and before handoff. While actively working, do this at least every 10 minutes, at the next tool boundary after a long operation. Fetch and pull safely, and perform the PR checks below; a Git fetch does not retrieve PR reviews or CI state. These checks happen during active execution; do not start unattended background polling when the chat is idle.
- Commit each coherent, verified unit of work as soon as it is ready. During longer work, aim for a checkpoint at least every 15 minutes; split the work into smaller valid units instead of leaving completed changes uncommitted. Do not create empty commits or knowingly broken changes just to meet the interval.
- Push the task branch immediately after every commit. Do not accumulate multiple local commits before pushing.
- After every successful push, update the task's open PR title and description to match the current implementation, verification results, and remaining work. Create a draft PR after the first push when no open PR exists for the task. Do not create duplicate PRs or repetitive progress comments.
- Before switching tasks, pausing, handing off, or sending the final response, commit and push any remaining coherent changes and bring the PR up to date. If synchronization is blocked, clearly report the incomplete step and reason.

## Start from the actual repository state

1. Inspect the working tree, staged changes, branch, upstream, remotes, and latest repository/task PR state before editing. Record pre-existing changes so they are not accidentally included. Fetch and assess incoming changes before starting the next unit of work.
2. Reuse the branch and open PR belonging to the current task. If working on the default/protected branch or a branch whose PR is already closed, create a task branch before committing. Do not move unrelated work or reuse an unrelated PR.
3. Identify the repository's required checks and the smallest meaningful verification for each planned unit.

## Pull safely and report interference

1. Fetch from the configured upstream remote, then compare local and upstream commits and inspect incoming file changes. Recheck the current branch and HEAD before mutating a shared working tree; an unexpected change from another chat is interference. If no upstream exists, inspect the known remote branch when available; do not guess a tracking branch or pull another branch into the task.
2. If the branch is up to date or only ahead, there is nothing to pull. If it is behind and can fast-forward, check incoming paths against local staged, unstaged, and untracked work, including rename and directory/file collisions and files currently being edited. A dirty working tree alone does not prohibit a pull when the changes are clearly independent.
3. When the fast-forward is safe, pull the configured upstream with `git pull --ff-only --no-autostash`. Review the incoming diff and rerun relevant checks if the incoming changes affect the task. Do not automatically merge the default branch into a feature branch.
4. Immediately tell the user when incoming changes overlap local work, the histories diverge, Git reports a conflict, another chat changes the branch or HEAD unexpectedly, or a detected interface change interferes with the current task. Name the branch and affected files, distinguish a possible overlap from an actual conflict, and state the blocked operation and a safe next step. Do not wait until the final response to disclose interference.
5. Pause only the affected synchronization and continue independent work where possible. Do not automatically stash, reset, discard changes, rebase, or create a merge commit to make the pull succeed. Ask for a decision only when reconciling the changes requires a choice about user intent or ownership. Resolve any actual conflict before treating synchronization as complete.

## Check the latest pull requests

1. List this repository's PRs by most recently updated activity, including newly created/updated open PRs and PRs merged or closed since the previous check. Start with recent activity on the first check; expand or paginate when necessary to cover updates since the previous check. Always inspect the task PR separately so a busy repository cannot hide it.
2. Keep a small in-chat baseline of the last check time, relevant PR numbers/states, and head/base SHAs. Inspect new or changed PR details and diffs when their scope overlaps the task or its dependencies. Refresh the task PR's current-head review and CI state even if its `updated_at` has not changed; CI can finish without a PR metadata update.
3. For the task PR and related PRs, check head/base changes, draft/open/merged/closed state, new reviews and comments, unresolved review threads, mergeability, and CI checks/workflow runs for the current head SHA. Recheck once after creating or updating the task PR; do not block indefinitely waiting for CI.
4. Immediately report findings that affect the task: relevant review requests or unresolved findings, failing current-head checks, confirmed merge conflicts, overlapping changes, or dependency/base changes. Include the PR link, affected files or dependency, and the practical next step. Handle in-scope findings under the current task and continue independent work when coordination is needed; do not silently expand the assignment to unrelated PRs.
5. Treat unavailable or pending checks and unknown mergeability as unverified, not as passing CI or a confirmed conflict. Old-commit results do not establish the current head's status. If access is blocked, report what could not be checked rather than claiming the latest PRs were reviewed.
6. These recurring checks are read-only. They do not authorize posting comments, approving reviews, resolving threads, merging/closing PRs, requesting reviewers, or rerunning workflows. Continue the already-required task PR title/body maintenance; preserve other contributors' PRs and comments.

## Commit a coherent unit

1. Review the diff and run the checks relevant to that unit. Fix failures caused by the change before committing. Report pre-existing failures or unavailable checks accurately; do not claim unrun checks passed.
2. Stage only the task's exact files or hunks. Avoid blanket staging. Preserve unrelated staged changes; inspect the actual commit scope before committing. Exclude credentials, generated output, and unrelated files.
3. Check the intended staged diff, including `git diff --cached --check`, and use a concise English commit message describing the change. Do not amend or rewrite existing commits unless explicitly authorized.
4. Proceed directly to push and PR synchronization.

## Push and maintain the PR

- Use the configured remote and task branch. Set the upstream on the first push when necessary. Do not invent or change remotes to bypass access problems.
- Use an available GitHub connector when it supports the required PR operations; otherwise use the repository's available CLI. With `gh`, pass multiline descriptions through a body file to preserve formatting.
- Keep the PR title and description focused on the resulting behavior and complete current scope. Include the checks actually performed, known failures or skipped checks, and any remaining work. Preserve repository templates and human-authored content when updating the relevant sections.
- Verify the push succeeded and the remote branch contains the local commit. Verify the PR points to the intended head/base and that its description reflects the latest push. Distinguish pending CI from passing CI.
- Do not force-push, delete remote branches, merge PRs, or request reviewers unless separately authorized.

## Blocked synchronization and handoff

- For permission, authentication, or network failures, use the environment's supported approval or authentication flow. Retry only after a concrete correction; never keep retrying unchanged failures or bypass restrictions. Report a blocked pull or interference promptly, even if other work can continue.
- If the directory is not a Git repository, no suitable remote is configured, or PR access is unavailable, do not initialize a repository or invent an external destination. Complete independent local work and report exactly which synchronization steps could not be completed.
- In the final handoff, state the incoming synchronization status, latest task commit, push status, PR link, verification results, material PR findings or unverified PR checks, and any task changes still uncommitted or unpushed. Keep unrelated pre-existing changes separate. Never describe a required synchronization step as complete without observing success.
