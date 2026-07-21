# Reference Audit — Phase F
**MEZO AI Platform — Phases F → I**
**Audited by:** MEZO AI engine (coding agent with local filesystem access)
**Date:** 2026-07-21
**Binding decision:** This document must exist and be approved before any plugin code is written.

---

## 1. `Ahmed_AI_Agent_Tools`

### 1.1 What It Is

A personal, high-capacity AI-agent toolkit built around a unified MCP (Model Context Protocol) gateway that combines ~2,695 actions across 54 backends. It is designed for local Docker/Fly deployment and covers: semantic software development (Serena LSP), repository automation (CodexPro), root terminal operations, file/archive operations, database access, browser automation, Docker MCP orchestration, GitHub/GitLab/Cloudflare/Telegram/Instagram/Google integrations, Linear/Jira task systems, and Grafana/Prometheus observability.

**Location:** `C:\Users\hyper\Desktop\mylove\MyAi\Ahmed_AI_Agent_Tools`
**License:** No LICENSE file found in the repository root or subdirectories. **Treat as all-rights-reserved / proprietary personal project.** → Do NOT copy any code. Adopt patterns and concepts only.

### 1.2 What Is Reusable (Pattern-Level Only)

#### ✅ Atomic Write Pattern (`actionLibTools.js` lines 123–126)
Write to a `.tmp` file first, then `rename()` atomically. If anything fails mid-write the original file is untouched.
**MEZO adoption:** `filesystem_plugin.py` will use the same approach: `write_file()` writes to `{target}.{random_hex}.tmp` then renames. This eliminates partial-write corruption.

#### ✅ Path Containment / Traversal Guard (`actionLibTools.js` lines 19, 25–26, 114–117)
- `abs(p, base)` resolves relative paths against a configured base, then checks the result is still inside the base.
- `safeArchiveName()` rejects entries starting with `/`, matching `C:/`, or containing `..` or null bytes.
**MEZO adoption:** `filesystem_plugin.py` and `shell_plugin.py` will use the same algorithm: `os.path.realpath(target)` must start with `os.path.realpath(MEZO_ALLOWED_ROOT)`, or the action is rejected before tier classification.

#### ✅ SHA-256 Copy Verification (`actionLibTools.js` `copyVerified()`, lines 40–61)
Hash source before rename; optionally compare to expected hash. Prevents silent corruption.
**MEZO adoption:** `filesystem_plugin.py` will hash after every `write_file()` and return the hash in the result record that goes into the audit log.

#### ✅ `readOnlyHint` / `destructiveHint` Tool Annotations (`actionLibTools.js` line 22)
Every registered tool declares `{ readOnlyHint: true }` or `{ readOnlyHint: false, destructiveHint: true }` as metadata alongside its schema.
**MEZO adoption:** This maps directly to MEZO's Tier system. Every `PluginAction` in `permission_guard.py` will carry a `tier: Tier` enum value as part of its declaration — not inferred at runtime, hard-declared at registration time. This is safer than runtime classification.

#### ✅ Secret Scan Pattern (`actionLibTools.js` `lib_secret_scan`, lines 127–140)
Regex patterns for private keys, Fly tokens, Telegram tokens, OAuth secrets, and generic `TOKEN=` / `API_KEY=` assignments. Used to scan files before committing.
**MEZO adoption:** Add a `SECRET_SCAN_PATTERNS` constant to `filesystem_plugin.py`. When `read_file()` is called on a path, warn (not block) if the file appears to contain secrets. When `write_file()` is called, scan content before writing and block if secrets are detected (they should come from env, not be written to files).

#### ✅ Tool Naming Convention (`skills/library/12-actions-reference.md`)
`action__server__tool` namespace (e.g. `action__serena__find_symbol`).
**MEZO adoption:** MEZO plugins use dot notation: `fs.read`, `fs.write`, `fs.delete`, `shell.run`, `git.status`, `git.pr_open`, `docker.list`, `docker.build`. This makes audit log entries readable at a glance.

#### ✅ "Inspect before mutate" Workflow Convention (`skills/library/42-github-operations.md`)
"Read repository metadata and branches → inspect open PRs → make the smallest requested change → verify target branch and commit SHA before writes or merges → re-read after mutation."
**MEZO adoption:** The `WorkflowEngine` step decomposition will enforce this as a default pattern: any workflow step that writes must be preceded by a read step that confirms the target state. This is enforced in `workflow_engine.py`, not just documented.

#### ✅ "Local-first, integrations are optional adapters" (`skills/library/55-local-first-architecture.md`)
"Prefer local binaries, Docker services and persistent storage. Account-backed services are optional adapters, not core dependencies."
**MEZO adoption:** Already embodied in MEZO's architecture (local Ollama first, Gemini fallback). Carried forward to plugins: `filesystem_plugin.py` and `shell_plugin.py` have zero external dependencies. `github_plugin.py` is only loaded if `GITHUB_TOKEN` is present.

### 1.3 What Is a Dead End

| Item | Why Dead End |
|---|---|
| `apps/gateway/` MCP gateway | MEZO uses its own FastAPI + SSE architecture, not MCP protocol |
| `packages/codexpro/` | Full CodexPro is a standalone system; MEZO builds its own minimal plugin layer |
| Full `skills/library/` (90 files) | Workflow playbooks for a different system; not directly importable |
| Archivers, tar, zip tools | MEZO doesn't need archive operations in Phase F-I |
| Telegram/Instagram/Google integrations | Out of scope for Phase F-I |
| Gateway authentication (token-based) | MEZO uses JWT auth from Phase -1 |

---

## 2. `colibri`

### 2.1 What It Is

A high-performance, single-file C runtime for running the GLM-5.2 744B Mixture-of-Experts model on consumer hardware by streaming experts from disk. Includes a web dashboard, a Tauri desktop shell, and an OpenAI-compatible HTTP gateway.

**Location:** `C:\Users\hyper\Desktop\mylove\MyAi\colibri`
**License:** Apache 2.0. GLM-5.2 weights are MIT. Code is copyable with attribution.

### 2.2 Lessons Already Captured (from Phases A-E)

| Lesson | Where Applied in MEZO |
|---|---|
| Engine / web / desktop separation | `mezo-ai-engine` / `mezo-frontend` / future desktop shell |
| OpenAI-compatible API surface (`openai_server.py`) | `mezo-ai-engine/main.py` FastAPI `/generate` follows same conventions |
| "Measure, don't assume" performance discipline | Provider latency logged in `provider_router.py` |
| Learning cache for hot experts (`.coli_usage`) | Inspiration for `user_model.py` — learn which patterns this user uses most |

### 2.3 What Is New for Phase F-I

**Nothing architecturally new.** Colibri is a model-runtime project. It has no plugin system, no permission model, no agent-control primitives, no audit log, no multi-step workflow engine, and no personalization system. Its domain does not overlap with what Phase F-I builds.

**One conceptual note:** Colibri's `.coli_usage` learning cache (records which experts your workload routes to, pins hottest ones automatically) is a physical-layer analogue of `user_model.py`'s behavioral learning. The pattern is the same — observe what's used most, cache it intelligently. This is already reflected in the `user_model.py` design.

### 2.4 Colibri Code That Could Be Copied (Apache 2.0)

None needed for Phase F-I. All relevant lessons are architectural patterns, not copyable algorithms.

---

## 3. Concrete Decisions Made from This Audit

| Decision | Source | Applied In |
|---|---|---|
| Atomic write via temp-rename | `actionLibTools.js` `copyVerified()` | `filesystem_plugin.py` `write_file()` |
| Path containment: `realpath()` inside `MEZO_ALLOWED_ROOT` | `actionLibTools.js` `abs()` + `safeArchiveName()` | `filesystem_plugin.py`, `shell_plugin.py` |
| Tier declared at registration, not inferred at runtime | `readOnlyHint` / `destructiveHint` | `permission_guard.py` `PluginAction` dataclass |
| Secret scan before write | `lib_secret_scan` patterns | `filesystem_plugin.py` write guard |
| Dot-notation action names in audit log | `action__server__tool` convention | All plugins: `fs.read`, `shell.run`, `git.pr_open` |
| "Read before write" enforced in step decomposition | `42-github-operations.md` workflow | `workflow_engine.py` |
| Local-first, integrations optional | `55-local-first-architecture.md` | Plugin loader: github/docker only loaded if credentials present |

---

## 4. What Was NOT Found (Important Negatives)

- **No sandboxing / seccomp / capability-dropping** in `Ahmed_AI_Agent_Tools`. Their model is full-root with no brakes (by design, for a personal trusted system). MEZO's tier + confirmation + kill-switch model is a deliberate inversion of that philosophy.
- **No per-user permission scoping** in either project. MEZO introduces this from scratch.
- **No workflow step visibility / SSE streaming** in either project. MEZO builds this from scratch.
- **No kill switch** in either project. MEZO builds this from scratch.

---

*This document satisfies the Section 5 requirement of the MEZO AI Full Autonomy Task spec. Plugin code development proceeds from here.*
