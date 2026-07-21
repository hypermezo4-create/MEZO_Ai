# Phase 1 acceptance report

Report date: 2026-07-21. Branch: `feat/mezo-agent-mvp`. This report separates locally verified evidence from deployment-dependent work. Phase 1 is **not complete** yet because Fly deployment, real Kilo execution against the target repository, remote CI, and the real Draft Pull Request have not been completed.

## Architecture implemented

- One public FastAPI application (`mezo-api`) serves the React interface and typed API.
- PostgreSQL models/migration cover users, repositories, projects, runners, tasks, steps, events, approvals, provider configuration, settings, and HMAC audit records.
- A separate private runner implements one-task leases, contained workspaces, low-privilege child processes, Kilo, real project checks, guards, cancellation, output streaming, cleanup, commit/diff evidence, and approved publish.
- GitHub App tokens are short-lived; the API independently verifies the pushed branch SHA and creates only a Draft PR.
- Gemini and OpenAI-compatible local provider routing fails explicitly and reports real health/usage.
- Obsolete Node backend, fake AI engine, in-memory task manager, old plugin routes, fake frontend health UI, and stale deployment definitions were removed.

## Verification evidence

| Check | Result | Evidence |
|---|---|---|
| Python syntax compilation | Pass | `python -m compileall -q mezo-control-plane mezo-runner`, exit 0 |
| API tests | Pass | 19 passed in 4.85s, exit 0 |
| Runner security tests | Pass | 12 passed in 2.27s, exit 0 |
| Frontend strict TypeScript | Pass | `tsc --noEmit`, exit 0 |
| Frontend tests | Pass | 5 passed, exit 0 |
| Frontend production build | Pass | Vite 5.4.21, 1,792 modules, exit 0 |
| Diff whitespace validation | Pass | `git diff --check`, exit 0 |
| Kilo CLI contract | Pass | Pinned 7.3.18 binary: `run --help`, configuration check, JSON-output flags, model flag, and skill discovery locally verified |
| Desktop Rust format/build | Pending | `cargo` is not installed in the current environment; CI provides the verification boundary |
| Integration workflow with mocked GitHub boundary | Pass | Durable task → lease → validation evidence → exact approval → publish authorization → GitHub SHA verification → Draft PR response; mismatch case also rejected |
| PostgreSQL migration on a real server | Pending | No PostgreSQL/Docker executable is available in the current environment |
| API and runner container builds | Pending | Docker is not installed in the current environment |
| Fly config validation/deployment | Pending | `flyctl` and Fly credentials are unavailable |
| GitHub Actions CI | Pending | Branch has not been pushed |
| Kilo live task | Pending | Runner image/deployment and Kilo credential are unavailable |
| `clean-code-guard` on this implementation | Pass | Manual skill guard pass completed after the final production-code edit; 12 findings fixed, 0 unresolved |
| `test-guard` on this implementation | Pass | Manual skill guard pass completed after the final test edit; boundary mocks assert observable outcomes and no unresolved findings remain |
| `docs-guard` on this implementation | Pass | Manual skill guard pass verified required paths, source-backed configuration/behavior, internal links, and absence of documentation stubs |
| Real target-repository Draft PR | Pending | Requires Fly deployment, successful checks/guards, and explicit approval |

## Definition-of-Done matrix

| Requirement | Status | Notes |
|---|---|---|
| Frontend creates a real durable task | Locally verified at API/UI test boundary | Real deployed browser run pending |
| Task survives API restart | Verified | Test creates a new TestClient against file-backed test DB; production source is PostgreSQL |
| Fly runner receives task | Not verified | Fly deployment pending |
| Authorized repository clone | Implemented, not live-verified | Every clone requires a repository/permission-scoped GitHub App token; live App validation pending |
| Kilo performs real task | Not verified | Credential/image deployment pending |
| Terminal output/live timeline | Verified in component/API contracts | Deployed run pending |
| Real diff/check/guard evidence | Implemented | Live target run pending |
| Failed checks prevent PR | Verified | API test |
| Approval binds exact diff and commit | Verified | Expiry, invalidation, and remote SHA mismatch tests |
| Real Draft PR URL | Not verified | No GitHub mutation performed; no URL claimed |
| PR remains Draft/unmerged | Not applicable yet | Implementation has no merge capability |
| No fake health/task/test/token data | Locally verified | Production-path search and clean-code guard are clean; remote CI pending |
| No committed secrets | Source review and `.gitignore`/`.dockerignore` controls | CI secret scan/operational secret setup pending |
| CI passes | Not verified | Workflow added; remote run pending |

## Database migration

`001_agent_mvp.up.sql` creates the complete Phase 1 schema and required indexes: user tasks, status/creation queue access, runner heartbeat, audit task ID, approval task ID, events, projects, and unique step ordering. `migrate.py` serializes migrations with a PostgreSQL advisory transaction lock. The down migration is reversible structurally but intentionally destructive to Phase 1 data and is restricted to empty/test recovery.

## Security controls

Implemented controls include Argon2, expiring signed JWT, roles, task ownership, owner-only security configuration/kill switch, explicit CORS, test-only SQLite, hashed runner tokens, private runner networking, OS privilege drop, root-only credentials/retention, allowed-root real paths, traversal/symlink tests, process-group cancellation, bounded/redacted logs, no shell evaluation, prohibited Git actions, exact approval, conditional guard enforcement, GitHub SHA verification, and serialized HMAC audit chaining.

## Known limitations

- No MFA/OIDC, password reset, refresh token, or user deactivation endpoint.
- Approval expiry requires cancelling/rerunning the task; Phase 1 does not reissue evidence in place.
- Per-task Unix isolation shares one runner container/kernel; there is no microVM or per-task cgroup quota.
- Validation command discovery covers common Node, Python, and shell repositories, not every ecosystem.
- Provider configuration stores model/endpoint/priority, while provider secrets remain environment/Fly secrets.
- Metrics are structured logs and API health/heartbeat fields; no Prometheus/OpenTelemetry backend is deployed.
- No browser runner, model worker, or interactive terminal input.
- A pushed branch can remain after a subsequent GitHub PR failure; branch deletion is deliberately not automated.

## Remaining acceptance procedure

1. Commit locally, obtain explicit authorization, push `feat/mezo-agent-mvp`, and confirm GitHub Actions passes.
2. Validate/build images and deploy PostgreSQL/API/runner with Fly secrets.
3. Capture API release ID, migration output, health response, real heartbeat/disk bytes, and restart-recovery evidence.
4. Authorize `hypermezo4-create/DeadZone_xiaomi-Lite` through the GitHub App.
5. Submit the required low-risk task through the web UI and let Kilo inspect instructions, implement, validate, and run guards.
6. Review commands, exit codes, diff, risks, PR preview, and audit trail.
7. Request explicit approval for the exact diff. Only then invoke publish.
8. Record the real Draft PR URL and verify GitHub marks it Draft and unmerged.
9. Update this report with evidence and only then evaluate the complete Definition of Done.
