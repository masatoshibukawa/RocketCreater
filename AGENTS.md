# Repository instructions

At the start of each active chat task about this repository, read and follow [.agents/skills/frequent-git-sync/SKILL.md](.agents/skills/frequent-git-sync/SKILL.md).

During active work, check for remote changes at the start, between work units, and at least every 10 minutes when tool control returns. Pull with `--ff-only` when safe. Immediately report overlapping edits, diverged history, or any risk of overwriting local work; pause the affected synchronization and continue independent work.

At the same checkpoints, check the repository's latest PR activity as well as the task PR: new and updated PRs, recent merges/closures, review comments and unresolved findings, current-head CI, and confirmed conflicts. Fetching Git refs alone does not check PR activity. Immediately report findings that affect the task, with the PR link and affected files or dependency. Keep pending or unavailable CI and unknown mergeability distinct from actual failures or conflicts.

For file-changing tasks, small, frequent commits, an immediate push after each commit, and an updated pull request after each push are mandatory throughout the task and before handoff. Do not defer all Git synchronization until the end.

Include only changes belonging to the current task. Preserve pre-existing changes and other contributors' work. Do not automatically stash, rebase, merge, or discard work to make a pull succeed. Explicit user restrictions on repository writes or Git synchronization take precedence.
