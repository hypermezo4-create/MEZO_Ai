# Troubleshooting

## API fails during startup

Production requires PostgreSQL plus non-empty bootstrap/runner-registration tokens and independent JWT/audit keys of at least 32 characters. `CORS_ALLOWED_ORIGINS` must be explicit and cannot contain `*`. Inspect the structured startup error; do not substitute SQLite or weaken configuration checks.

Check database health with:

```bash
curl -fsS https://<api-host>/healthz
```

If a migration release failed, inspect the release logs and fix the migration or database connectivity. The advisory lock deliberately prevents concurrent migration writers.

## Owner bootstrap returns 409

Bootstrap is one-time. Sign in with an existing owner. If ownership is lost, follow a separately approved database recovery procedure; do not add a default password or reopen bootstrap by deleting users casually.

## Login returns 401

Verify email/password, user active state, server clock, JWT secret continuity, issuer/audience, and token expiry. Arbitrary identity headers do nothing. Restarting with a different JWT secret invalidates prior access tokens by design.

## Browser reports CORS failure

Add the exact HTTPS origin to `CORS_ALLOWED_ORIGINS` and redeploy. Do not use `*`. Same-origin web builds served from `mezo-api` need no cross-origin exception. Tauri builds need their configured remote API origin allowed.

## Runner does not register

Confirm private DNS reaches `http://mezo-api.internal:8080`, registration secrets match, and the runner name is unique. If the persistent identity exists, registration is skipped and its bearer token is used. If the identity was lost but the name remains registered, deliberately retire that database runner record or use a new name under owner-controlled recovery.

## Runner appears offline

The UI marks a runner offline from real heartbeat age. Check Machine state, private network, API health, runner JSON logs, and volume permissions. Actual disk totals are reported from `/workspaces`; there is no fallback value.

## Task stays queued

Check kill-switch state, online runner capacity, runner logs, and whether that runner already owns a non-terminal task. A single runner executes one privileged task. An expired lease is recovered when a runner requests another lease.

## Task restarts after runner failure

This is expected after lease expiry. Startup cleanup removes the partial workspace and the retry starts from a new clone. Tasks, steps, events, and approval state remain in PostgreSQL. Review the `lease_recovered` event and do not reuse unvalidated partial files.

## Clone returns 503

The GitHub App is not configured or token exchange failed. All production clones require a token restricted to the authorized repository, including public repositories. Verify App ID, installation ID, private key format, repository installation, API reachability, and App contents permission. Never add an anonymous fallback or broad PAT as a shortcut.

## Kilo fails or returns no changes

Check the pinned CLI is installed (`kilo --version`), an explicit model credential/model is configured, task-local Kilo permissions match the pinned CLI schema, and the repository task is actionable. Empty plans and no-change implementations fail explicitly.

## Validation or guards fail

Open the right-panel terminal, tests, and guards. Repository checks remain authoritative. `clean-code-guard` is always required; test/docs guards are mandatory only for applicable changes. A missing PASS marker is a failure. Fix the implementation and run a new task; do not edit the approval record or weaken checks.

## Approval is expired or invalidated

No publish can occur. Cancel the task and rerun it to generate current evidence and a new approval. Approval cannot be copied between tasks or diffs.

## Draft PR creation fails after push

Check the task error and audit log. Common causes are approval expiry, local/approved/GitHub SHA mismatch, App permission, branch conflict, wrong installation, or GitHub outage. MEZO intentionally marks the task failed rather than claiming success. Inspect the pushed branch manually and delete it only through a separately authorized process; Phase 1 has no branch-delete endpoint.

## Audit integrity is false

Stop external writes, preserve database and API logs, and investigate the first broken hash or signed-head mismatch. Verify `AUDIT_HMAC_KEY` continuity. This system is tamper-evident, not immutable; do not “repair” hashes before incident evidence is captured.

## Cancellation does not finish promptly

The runner sends SIGTERM to the process group and SIGKILL after five seconds. Check for an uninterruptible kernel I/O state and Machine health. After runner loss, the durable lease recovery path prevents an in-memory orphan from being considered complete.

## Docker/Fly validation unavailable locally

Install supported Docker and `flyctl`, then run the commands in `docs/fly-deployment.md`. Absence of those CLIs is not evidence that images or Fly deployment succeeded.
