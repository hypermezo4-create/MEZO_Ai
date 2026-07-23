# Fly cluster deployment

Run from the repository root with cached Fly authentication for the `personal` organization:

```powershell
powershell -ExecutionPolicy Bypass -File mezo-deployment/deploy-cluster.ps1 -Stage 1
# run the Stage 1 acceptance test, then:
powershell -ExecutionPolicy Bypass -File mezo-deployment/deploy-cluster.ps1 -Stage 2
powershell -ExecutionPolicy Bypass -File mezo-deployment/deploy-cluster.ps1 -Stage 3
```

`-Stage all` performs the same sequence in one invocation. The script is idempotent: it checks app, volume, database, and Machine inventory, refuses conflicting volume sizes, and enforces a maximum of 20 MEZO application Machines.

## Persistent resources

- Valkey: one encrypted 20 GB volume.
- Indexer: one encrypted 100 GB volume.
- Runners: four separate encrypted 500 GB volumes.
- Qwen Coder: two separate encrypted 250 GB volumes.
- GLM: two separate encrypted 300 GB volumes.
- DeepSeek: two separate encrypted 200 GB volumes.
- Vision: two separate encrypted 250 GB volumes.
- Fast Qwen: two separate encrypted 100 GB volumes.
- Embedding and reranker: one encrypted 100 GB volume each.
- Managed Postgres: Launch plan, PostgreSQL 17, 100 GB.

Fly volumes are host-local, cannot be shared between Machines, do not automatically replicate, and remain billable while Machines are stopped. Automatic snapshots and network usage add cost. Managed Postgres is independent and remains highly available according to the selected Fly plan.

## Secrets

The deployment script generates model, runner, orchestration, and Valkey credentials in memory and imports them over stdin. Values are never written to source files or printed. Managed Postgres attachment creates `DATABASE_URL` directly as a Fly secret. GitHub credentials are optional and absent from basic operation.

## Access

No app exposes public ports. Use `mezo web`, the desktop client, or:

```powershell
fly proxy 8787:8080 --app mezo-web --bind-addr 127.0.0.1
```

Then open `http://127.0.0.1:8787`. Public unauthenticated command execution is impossible without membership in the Fly organization and its WireGuard tunnel.

## Rollback

Roll back application releases with `fly releases` and `fly deploy --image ...` without deleting volumes. Do not delete or shrink model/workspace volumes during application rollback. Database schema changes must remain backward compatible until every service is confirmed healthy.
