# Security model and threat model

## Assets and trust boundaries

Protected assets are user credentials, JWT signing material, the audit HMAC key, runner registration/identity tokens, GitHub App private key and installation tokens, Kilo/provider keys, repository content, approved diffs, PostgreSQL records, and unrelated workspaces.

The public client is untrusted. `mezo-api` is the policy authority. PostgreSQL is trusted for availability and state, but audit integrity is independently checked with an HMAC key held outside the database. The runner daemon is trusted control code; cloned repositories, build scripts, Kilo output, and task commands are untrusted. GitHub and configured model providers are external trust boundaries.

## Threats and controls

| Threat | Implemented control | Residual risk |
|---|---|---|
| Forged user identity | Argon2 password verification and issuer/audience/expiry-checked JWT; no `X-User-ID` trust | No MFA or external IdP in Phase 1 |
| Cross-user task access | Task ownership checks; owners alone may see all tasks | Owners are intentionally privileged |
| CSRF | Bearer tokens are held in memory and never sent automatically as cookies | A compromised frontend origin can act as the signed-in user until token expiry |
| CORS abuse | Production requires an explicit environment allowlist and rejects `*` | Operators must keep the allowlist narrow |
| Secret exposure in logs | Bounded environment passed to child processes; token/header/private-key redaction; event size limits | Novel secret formats may evade pattern redaction; provider keys are still available to the Kilo process that needs them |
| Repository code reading runner credentials | Daemon runs as root, credentials are root-only, task processes drop supplementary groups and run as UID/GID 10002 with a clean environment | This is container/Unix isolation, not a separate microVM per command |
| Workspace traversal or symlink escape | Canonical real-path containment, safe IDs, forbidden symlink escapes, exact cleanup depth, startup stale cleanup | Kernel or container-runtime vulnerabilities are out of scope |
| Reading an earlier retained workspace | Successful workspaces are deleted; retained failures are recursively root-owned and mode-restricted before another task | Manual host administrators can access the volume |
| Destructive shell or Git behavior | No shell interpolation; executable allowlist; deny force/hard arguments; Git push blocked except the one authorized non-force call; Docker socket is not mounted | Repository test scripts can perform arbitrary computation and network calls as the task UID |
| Kilo bypassing MEZO | Deny-by-default Kilo permissions, external-directory denial, workspace-only execution, no runner/API/GitHub credential in Kilo environment | Kilo CLI behavior must remain compatible with the pinned version |
| Approval replay or changed diff | Approval stores task, user, action, expiry, diff hash, snapshot, and validated commit; one task cannot use another approval | An owner with direct database access can alter application state, which audit verification should expose but cannot prevent |
| Different commit pushed after approval | Runner checks local SHA; API checks callback SHA; API independently reads the GitHub branch ref before PR creation | GitHub availability can block publication |
| Accidental merge or force-push | No merge endpoint or GitHub method; command guard rejects force flags; app permissions exclude merges | A separately privileged human or application can still act outside MEZO |
| Fake success or telemetry | API rejects failed checks, missing clean-code guard, conditional guard omissions, invalid PR URLs, and provider failures; hardware/disk values come from runner heartbeat | CI/Fly status is not available until deployed |
| Audit file editing | Append chain is HMAC-SHA256; PostgreSQL advisory lock serializes writers; signed head and full chain are verified on reads | It is tamper-evident, not immutable. An attacker with both database write access and the HMAC key can forge history; key loss prevents verification |
| Runaway output/process | Process-group TERM/KILL, command timeouts, 2 MB capture cap, 16 KB event cap | Resource quotas beyond the Fly Machine limits are not cgrouped per task in Phase 1 |

## Authentication and authorization

The bootstrap route works only while the user table is empty and requires a separately provisioned token. Passwords require at least 12 characters and are stored only as Argon2 hashes. Access tokens expire (30 minutes by default). Roles are `owner`, `operator`, and `viewer`.

Owners manage users, repository authorization, provider configuration, the kill switch, and infrastructure credentials outside the application. Operators can create and operate their own tasks and approve their own exact-diff external write. Viewers have read-only authenticated access to records permitted by ownership rules. No production default password exists.

## Secret lifecycle

Fly secrets provide database, JWT, audit, bootstrap, runner-registration, GitHub App, and model credentials. The GitHub App private key stays in the API. The runner receives repository-scoped installation tokens only for clone and approved publish windows. Tokens are passed through environment-backed `GIT_ASKPASS`, never embedded in a remote URL, and the script is removed in `finally` blocks.

The repository must never contain `.env`, runner identity, task workspace, database dump, private key, access token, or provider credential. `.dockerignore` excludes environment files and build/runtime directories. Every installation token request names only the task repository and downgrades permissions for clone, push, branch verification, or Draft PR creation.

## Emergency control

Only an authenticated owner can arm or disarm the durable kill switch. Disarmed state blocks new leases. Cancellation remains available and terminates the active process group. Phase 1 does not expose any root shell, production deploy, secret rotation, database deletion, GitHub permission mutation, branch deletion, force-push, or merge endpoint.
