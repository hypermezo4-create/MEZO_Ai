# Permission policy

MEZO classifies actions before execution. The API is authoritative even when Kilo runs with automatic tool use.

| Tier | Examples | Phase 1 behavior |
|---|---|---|
| 1 — read-only | Repository reads, `git status`, `git diff`, `git log`, health and test-result reads, static analysis | Automatic inside the assigned task |
| 2 — reversible workspace | Create working branch, edit, install dependencies, lint, test, format, `git add`, local commit | Automatic only inside the contained workspace under the task UID |
| 3 — external write | Push working branch, create Draft PR, task artifact upload | Exact-diff policy authorization, audit record, and explicit UI approval/publish action required. Phase 1 implements only non-force branch push and Draft PR |
| 4 — irreversible/production | Merge, force-push, delete remote branch, deploy production, rotate secrets, delete database data, change GitHub/Fly permissions | Disabled. Cancellation and owner-only emergency shutdown are the only control-plane exceptions |

## Enforcement points

The frontend presents evidence but is not a security boundary. The API validates role, task ownership, task state, approval state, expiry, diff hash, validation report, guard applicability, and commit SHA. The runner checks allowed executable/arguments, canonical working directory, Kilo permissions, local commit identity, and the publish command returned by the API. GitHub’s branch ref is the final independent commit check.

Kilo cannot push, create a PR, deploy, use Docker, or access external directories. The runner—not Kilo—performs the one approved `git push`. The API—not Kilo or the runner—calls GitHub to create a Draft PR.

## Approval object

An approval stores `task_id`, `diff_hash`, `user_id`, `action`, `expires_at`, state, decision time, and a complete evidence snapshot: repository, base/working branch, changed files, diff summary, commands, tests, guards, risks, PR title/body, and commit SHA.

Approval is rejected when it is absent, expired, already decided, for a different diff, for a different task, or when validation/guards are not successful. Changing the stored diff invalidates the approval. Publication is a separate deliberate action after approval. No approval can authorize a merge.

## Guard applicability

The sequence is implementation, project checks, `clean-code-guard`, conditional `test-guard`, conditional `docs-guard`, then post-guard project checks. The API requires `test-guard: passed` when changed paths look like tests and `docs-guard: passed` for Markdown, MDX, reStructuredText, or `docs/` changes. A skipped applicable guard is a hard failure.
