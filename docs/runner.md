# Runner

## Image and machine

`mezo-runner/Dockerfile` builds a CPU-only Debian/Node 22 image with Git, GitHub CLI, Docker CLI (no daemon/socket), Kilo CLI 7.3.18, Python 3, Node/npm, pytest 8.4.1, Ruff 0.15.22, ShellCheck, ripgrep, jq, C/C++ build tools, CMake, and Skills CLI 1.5.19. The three guard skills are copied from `amElnagdy/guard-skills` at commit `ffa26036b7b5e77b20b5d679304a703b6fd1a43d`.

Kilo is deliberately pinned to 7.3.18 because newer Linux package availability must be revalidated before upgrade. The Fly definition requests `performance-16x` and mounts a separately created 500-GB volume at `/workspaces`; deployment acceptance must confirm the Machine allocation is CPU-only with 128 GB RAM.

## Registration and lease

On first boot, the daemon exchanges `RUNNER_REGISTRATION_TOKEN` for a random runner bearer token. It stores only the assigned runner ID/token in `/workspaces/.runner/runner-identity.json`, mode 0600 in a root-only directory. The API stores only SHA-256 of the bearer token. Subsequent restarts reuse the identity.

The daemon reports actual disk totals/free bytes and status every 10 seconds. It leases at most one non-terminal task. The API rejects a second active lease. Lease expiry returns interrupted provisioning/planning/running/validating tasks to the queue; startup removes stale task workspaces before such a retry.

## Isolation

Every task path is `/workspaces/<user-id>/<task-id>`. IDs accept only letters, digits, underscore, and hyphen. All runner filesystem methods resolve real paths against the task root, reject traversal and symlink escapes, and refuse broad cleanup.

The daemon remains root so it can protect its credential and drop privileges. Every repository/Kilo/validation process runs with empty supplementary groups as UID/GID 10002, umask 077, a task-local home, an allowlisted environment, and no runner registration/identity token. Root-owned `.runner` state is not traversable by the task UID. The Docker socket, Fly token, database URL, GitHub App private key, and control-plane signing secrets are absent.

Only one privileged task runs at once. Successful/cancelled workspaces are deleted. Failed workspaces are also deleted by the production default; if `FAILED_WORKSPACE_RETENTION=keep`, they are recursively changed to root ownership and restrictive modes before another task can start.

## Command policy

Commands use `asyncio.create_subprocess_exec`; no command string is evaluated by a shell. Executables are allowlisted. Git push/update-ref/replace/notes and force/hard arguments are denied. The sole exception is a non-force push to the task's authorized GitHub URL after the API returns an approved publish command.

Each command emits start, stdout/stderr, finish, exit code, working directory, timestamp, and duration. Output is redacted, streamed in bounded chunks, and capture is capped at 2 MB per stream. Timeout or cancellation signals the whole process group with SIGTERM, waits five seconds, then sends SIGKILL.

## Kilo phases

The runner requires an explicit `KILO_MODEL`, writes a task-local Kilo configuration, and invokes the pinned CLI with `run --pure --auto --format json --model`. The same policy is injected through `KILO_CONFIG_CONTENT`, and repository-level Kilo configuration is disabled so cloned code cannot override it. Planning is read-only. Implementation permits edits but keeps a deny-by-default command map containing only repository-inspection Git commands and installed skill reads. External directories, Git push, Docker, deployment, external plugins, project scripts, and arbitrary shell commands are denied. MEZO later runs detected installs/tests in a separate sanitized process without model credentials. Raw JSON events are streamed and the runner extracts plan/guard text only from `text` events; malformed structured output fails the task.

Kilo receives only its generated non-secret policy, model ID, auto-update/project-config controls, and the configured `KILOCODE_API_KEY`, `KILO_API_KEY`, `GEMINI_API_KEY`, or `OPENAI_API_KEY`. Arbitrary `KILO_*` environment values are not forwarded. It never receives MEZO API, database, Fly, GitHub App, registration, or runner identity credentials.

## Validation and guards

The runner detects safe commands from repository files: locked npm install and declared lint/typecheck/test/build scripts, Python requirements/pytest, ShellCheck for shell files, and `git diff --check`. It records all exit codes and reruns validation after guards.

`clean-code-guard` always runs. `test-guard` runs when tests changed. `docs-guard` runs when documentation changed. A guard must produce a completed Kilo `skill` tool event for the expected skill, exit zero, and emit `MEZO_GUARD_RESULT: PASS`; otherwise the task fails. Guards review but do not replace repository checks.

## Publication

The runner commits locally before approval, submits diff/evidence/commit SHA, and waits. It rechecks local `HEAD` against the API’s approved SHA. It receives a short-lived installation token only for the push, uses `GIT_ASKPASS`, and removes the script even on error. The push names the authorized GitHub URL directly and disables repository hooks, credential helpers, and inherited HTTP extra headers. The API independently verifies GitHub’s ref and creates the Draft PR.

## Safe upgrade checklist

Rebuild and run workspace traversal, symlink, cancellation, timeout, environment, branch-policy, and cleanup tests. Confirm the pinned Kilo config schema and CLI flags against official docs. Inspect package install output, run an unprivileged sample task, verify `/workspaces/.runner` cannot be read by UID 10002, and never mount `/var/run/docker.sock` into the runner.
