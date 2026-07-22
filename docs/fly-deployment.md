# Fly.io deployment and rollback

The repository defines `mezo-api` and private `mezo-runner` applications. It does not provision a single-volume database. Use Fly Managed Postgres or another highly available PostgreSQL service and treat its connection string as a secret.

## Prerequisites

- Fly organization, authenticated `flyctl`, and access to create Machines/volumes.
- PostgreSQL 17-compatible database reachable by `mezo-api`.
- GitHub App ID, installation ID, and PEM private key.
- Kilo/model credential.
- Strong independent JWT, audit HMAC, bootstrap, and runner-registration secrets.
- Region quota for the requested `performance-16x` Machines and two 500 GB volumes; deployment acceptance must confirm that each allocated application Machine is CPU-only with 128 GB RAM.

Do not put any value from this list in `fly.toml`, an image, a shell history shared with others, or source control.

## Create applications and volumes

From the repository root:

```bash
fly apps create mezo-api
fly apps create mezo-runner

fly volumes create mezo_api_data \
  --app mezo-api \
  --region ams \
  --size 500

fly volumes create mezo_runner_data \
  --app mezo-runner \
  --region ams \
  --size 500
```

Every API Machine requires its own 500 GB volume mounted at `/data`, and every runner Machine requires its own 500 GB volume mounted at `/workspaces`. A Fly volume is tied to one app, Machine, server, and region; it cannot be shared between Machines and volumes do not automatically replicate. Scaling either app requires another dedicated 500 GB volume for every new Machine. Keep max runner task concurrency at one per Machine.

Managed Postgres remains independent from both application volumes. Do not store PostgreSQL files, secrets, private keys, Fly credentials, model credentials, JWT secrets, audit secrets, or runner-registration secrets on either application volume. The volumes are not database backups and do not provide high availability. Volume charges continue while Machines are stopped, and snapshots and network usage may add additional cost.

A single Machine with one local volume has host-level availability risk and will have downtime during deployment or host failure. Keep the `rolling` deployment strategy for attached volumes; do not use canary or blue-green deployment with these Machines.

## Configure API secrets

Generate secrets with a cryptographic random generator. Convert the GitHub PEM newlines in the manner accepted by `fly secrets set`; do not paste a private key into a committed file.

```bash
fly secrets set --app mezo-api \
  DATABASE_URL='postgresql+psycopg://...' \
  JWT_SECRET='...' \
  AUDIT_HMAC_KEY='...' \
  MEZO_BOOTSTRAP_TOKEN='...' \
  RUNNER_REGISTRATION_TOKEN='...' \
  CORS_ALLOWED_ORIGINS='https://mezo-api.fly.dev' \
  GITHUB_APP_ID='...' \
  GITHUB_INSTALLATION_ID='...' \
  GITHUB_APP_PRIVATE_KEY='...'
```

Configure Gemini/local provider secrets on the API only if that provider route is used. The Kilo credential belongs on the runner, not the API, unless the same provider is deliberately used in both places.

```bash
fly secrets set --app mezo-runner \
  RUNNER_REGISTRATION_TOKEN='same registration secret as API' \
  KILOCODE_API_KEY='...' \
  KILO_MODEL='explicit-model-id'
```

After the first successful registration, rotate or remove the registration secret only after ensuring the runner identity file persists. Keep a recovery procedure for deliberately re-registering a runner name.

## Validate and deploy

```bash
fly config validate --config mezo-deployment/fly/mezo-api.toml
fly config validate --config mezo-deployment/fly/mezo-runner.toml

fly deploy --config mezo-deployment/fly/mezo-api.toml --remote-only
fly deploy --config mezo-deployment/fly/mezo-runner.toml --remote-only
```

The API release command runs `python /app/database/migrate.py up` under a PostgreSQL advisory lock. A failed migration prevents rollout. The runner has no public service section and calls `http://mezo-api.internal:8080` on Fly private networking.

## Post-deployment checks

1. `GET https://mezo-api.fly.dev/healthz` returns database `available`.
2. Bootstrap the first owner once, then rotate/remove the bootstrap secret.
3. Authorize only the intended GitHub App installation repository.
4. Confirm `/api/runners` shows a recent real heartbeat and actual disk bytes.
5. Disarm/arm the kill switch as owner and verify a non-owner receives 403.
6. Submit a read/validation task before any mutation task.
7. Restart the API during a queued or waiting task and verify the task remains.
8. Run the required `DeadZone_xiaomi-Lite` task, inspect every command/diff/guard result, approve the exact diff, then separately request Draft PR creation.
9. Confirm GitHub shows a Draft and no merge occurred.

## Graceful shutdown and recovery

Fly sends SIGTERM. The API has a 30-second kill timeout. The runner has 60 seconds, cancels the process group, and relies on durable lease recovery if interrupted. A runner restart deletes stale task workspaces; the API requeues the task only after its lease expires.

## Application rollback

List releases and redeploy a previously known image/revision according to current Fly CLI capabilities. Do not roll application code back across an incompatible database schema.

For migration `001_agent_mvp`, the down migration drops all Phase 1 data and is destructive. It exists for empty/test rollback only:

```bash
python mezo-database/migrate.py down --version 001_agent_mvp
```

For production rollback, prefer forward-fixing code and schema. Before any schema rollback, disarm leases, stop the runner, take a verified database backup, confirm the target release compatibility, and obtain explicit owner authorization. Never treat the runner volume as a database backup.

## Deployment status

The configuration is committed but has not been validated by `flyctl` or deployed from the current development environment, because Fly CLI/credentials are unavailable here. The acceptance report must be updated with real release IDs, health output, restart evidence, and runner volume size after deployment.
