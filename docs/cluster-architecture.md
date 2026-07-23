# Private 20-Machine architecture

The cluster contains one web/API, one router, one Valkey coordinator, one indexer, four runners, and twelve CPU model Machines. All processes listen on their Fly 6PN interfaces and no application has public ports or public IP allocations. Local clients reach only `mezo-web:8080` through an authenticated Fly WireGuard tunnel bound to `127.0.0.1:8787`.

The task flow is web → Valkey → one runner → router → specialist model. Normal coding uses Qwen Coder, DeepSeek review, Qwen correction, then isolated tests. Complex planning adds GLM. Vision requests use Qwen VL. Indexing calls Qwen Embedding and Qwen Reranker. Every model call uses an internal Fly secret and has no cloud fallback.

Runner commands execute inside bubblewrap namespaces with a read-only host root, a single writable task workspace, a private temporary directory, a dedicated unprivileged UID, process-group cancellation, bounded output, and an executable/argument allowlist. Git push remains prohibited in the basic flow.

PostgreSQL stores conversations, projects, tasks, events, machine registry, index metadata, and audit records. Valkey stores ephemeral queue, cancellation, lock, stream, and model-availability coordination state. Each runner and model Machine has a dedicated encrypted Fly volume; volumes are never shared.
