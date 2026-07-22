# Task lifecycle

## Durable states

| State | Entered when | Valid next states |
|---|---|---|
| `queued` | User creates task or expired lease is recovered | `provisioning`, `cancelled`, `failed` |
| `provisioning` | Runner obtains row-locked lease | `planning`, `cancelled`, `failed` |
| `planning` | Workspace exists; clone and instruction/plan phases run | `running`, `cancelled`, `failed` |
| `running` | Kilo implementation starts | `validating`, `cancelled`, `failed` |
| `validating` | Repository checks and guards run | `waiting_for_approval`, `cancelled`, `failed` |
| `waiting_for_approval` | Exact diff, checks, guards, PR preview, and commit are stored | `creating_pull_request`, `cancelled`, `failed` |
| `creating_pull_request` | User approved exact diff and explicitly requested publish | `completed`, `cancelled`, `failed` |
| `completed` | GitHub returned a real Draft PR URL | Terminal |
| `failed` | A required invariant, command, guard, provider, or GitHub operation failed | Terminal |
| `cancelled` | User cancellation/rejection terminates or prevents execution | Terminal |

Transitions are centralized and invalid transitions return HTTP 409. `started_at` is set at first provisioning; terminal states set `finished_at`. `runner_id`, `workspace_id`, current step, error, approval state, and PR URL remain durable across API restart.

## Step states

Steps are created up front: workspace, clone, instructions, plan, implementation, validation, guards, approval, and Draft PR. A step moves from `pending` to `running`, `skipped`, or `blocked`; running steps finish as `completed`, `failed`, or `waiting_for_approval`. Approval steps resume from `waiting_for_approval`. Invalid step changes also return HTTP 409.

Each step stores timestamps, command, exit code, summary/error, and whether approval is required. Terminal command evidence is additionally stored as ordered task events and delivered through SSE.

## Lease recovery

Leases expire after 120 seconds by default. Leasing uses PostgreSQL row locks with `SKIP LOCKED`. When a runner asks for work, expired active tasks are reset to queued and detached from the prior runner before the oldest queue item is selected. A runner cannot hold two active tasks.

The heartbeat refreshes observable runner state while every command event/transition extends the task lease. On runner restart, stale local workspaces are removed; after the database lease expires the task receives a new isolated clone. Recovery is allowed only from provisioning, planning, running, or validating. It resets the step projection to pending while retaining the prior attempt in durable task events and the signed audit chain.

## Approval lifecycle

`pending` approvals can become `approved`, `rejected`, `expired`, or `invalidated`. They expire after 30 minutes by default. Rejection cancels the task. A changed diff invalidates the approval. Approved state alone does not publish: the user must invoke the Draft PR action, which moves the task to `creating_pull_request`.

If GitHub ref verification or Draft PR creation fails, the task becomes failed and records the external-write failure. MEZO never marks completed before GitHub returns an `html_url` from a 201 Draft PR response.

## Cancellation

Queued or approval-waiting tasks transition immediately to cancelled. Active tasks set a durable cancellation request. The next heartbeat tells the owning runner, which terminates the process group and records cancellation. No parent-only cancellation is used.
