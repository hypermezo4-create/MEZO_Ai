# MEZO AI

MEZO is an Apache-2.0, single-user coding agent whose inference, indexing, conversations, and isolated workspaces run on a private Fly.io CPU cluster. The local computer is only a terminal, desktop, and browser client. No MEZO login or paid model API is used.

## Components

- `mezo-control-plane`: private web/API with PostgreSQL conversations and task state.
- `mezo-router`: specialist routing, parallel review, timeouts, and circuit breakers.
- `mezo-queue`: private Valkey task coordination and cancellation.
- `mezo-indexer`: repository maps, embeddings, and reranking.
- `mezo-runner`: four bubblewrap-isolated coding workers.
- `mezo-model-server`: checksum-pinned CPU `llama.cpp` model services.
- `mezo-frontend`: ChatGPT-style task, terminal, file, and diff interface.
- `mezo-cli` and `mezo-desktop`: auto-reconnecting private Fly tunnel clients.

## Build and test

```bash
python -m pip install -r mezo-control-plane/requirements-dev.txt
python -m pip install -r mezo-runner/requirements.txt pytest-asyncio
npm ci
python -m compileall -q mezo-control-plane mezo-router mezo-indexer mezo-runner mezo-model-server
python -m pytest mezo-control-plane/tests
python -m pytest mezo-runner/tests
npm run typecheck --workspace=mezo-frontend
npm test --workspace=mezo-frontend
npm run build --workspace=mezo-frontend
cargo check --manifest-path mezo-desktop/src-tauri/Cargo.toml
```

Build every container from the repository root using the corresponding Dockerfile. Model downloads occur only at runtime onto encrypted Fly volumes and are verified against the manifests.

## Private clients

Install the Windows terminal command with `powershell -File mezo-cli/install.ps1`, then use `mezo`, `mezo web`, `mezo chat`, `mezo run "task"`, or `mezo doctor`. The client invokes `fly proxy` against `mezo-web` and binds only `127.0.0.1:8787`.

Build the desktop application with `npm run build --workspace=mezo-desktop`. It starts the same private tunnel and opens the local UI without credentials.

## Deployment

`mezo-deployment/deploy-cluster.ps1` implements the authorized three-stage, idempotent deployment. It creates no public IPs, generates internal credentials without printing them, creates exactly the documented volumes, and fails if the MEZO application Machine count would exceed 20.

See [cluster architecture](docs/cluster-architecture.md), [deployment](docs/fly-deployment.md), and [third-party licenses](THIRD_PARTY_LICENSES.md).
