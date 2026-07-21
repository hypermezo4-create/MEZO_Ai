# MEZO deployment

Phase 1 deploys exactly two applications: public `mezo-api` and private `mezo-runner`. Use `fly/mezo-api.toml` and `fly/mezo-runner.toml`; obsolete backend, AI-engine, Kubernetes, Terraform, and Vercel definitions were removed because they did not represent the production architecture.

The API image builds and serves the React frontend. PostgreSQL must be an external highly available service; it is not stored on a runner volume. The runner needs one 500 GB volume mounted at `/workspaces` and executes one task at a time.

For secrets, creation, validation, deployment, checks, and rollback, follow [`docs/fly-deployment.md`](../docs/fly-deployment.md). For a local PostgreSQL/API stack, use `docker/docker-compose.yml` with non-committed environment values.
