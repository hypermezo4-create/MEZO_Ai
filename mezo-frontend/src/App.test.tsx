import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import App from "./App"


const step = (status = "pending") => ({ id: "step-1", step_index: 0, name: "validation", description: "Run tests", status, started_at: null, finished_at: null, command: null, exit_code: null, result_summary: null, error: null, requires_approval: false })
const task = (status: string, overrides = {}) => ({
  id: "task-1", user_id: "user-1", repository: "owner/repo", base_branch: "main", working_branch: "mezo/task-1",
  title: "Repair validation", description: "Fix it", status, current_step: null, created_at: "2026-01-01T00:00:00Z",
  started_at: null, finished_at: null, runner_id: "runner-1", workspace_id: "user-1/task-1", error: null,
  approval_state: "none", pull_request_url: null, changed_files: [], diff_text: null, diff_hash: null,
  validation_report: {}, steps: [step()], ...overrides,
})

function response(data: unknown, status = 200) { return Promise.resolve(new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } })) }

function installFetch(tasks: unknown[]) {
  const fetchMock = vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith("/api/auth/login")) return response({ access_token: "token", expires_in: 1800 })
    if (url.endsWith("/api/repositories")) return response([{ id: "repo-1", full_name: "owner/repo", default_branch: "main", active: true }])
    if (url.endsWith("/api/projects")) return response([])
    if (url.endsWith("/api/tasks") && init?.method === "POST") return response(task("queued"), 201)
    if (url.endsWith("/api/tasks")) return response(tasks)
    if (url.endsWith("/api/runners")) return response([{ id: "runner-1", name: "fly-runner", status: "offline", version: "1", current_task_id: null, last_heartbeat_at: "2026-01-01", disk_total_bytes: null, disk_free_bytes: null, capabilities: {} }])
    if (url.endsWith("/api/audit")) return response({ integrity_valid: true, records: [] })
    if (url.includes("/events")) return Promise.resolve(new Response(null, { status: 200 }))
    if (url.endsWith("/api/tasks/task-1/approval")) return response({ id: "approval-1", task_id: "task-1", diff_hash: "a".repeat(64), action: "create_draft_pull_request", state: "pending", expires_at: "2099-01-01T00:00:00Z", request: { repository: "owner/repo", base_branch: "main", working_branch: "mezo/task-1", changed_files: [{ path: "src/safe.ts", additions: 2, deletions: 1 }], diff_hash: "a".repeat(64), commit_sha: "b".repeat(40), diff_summary: { files: 1, additions: 2, deletions: 1 }, commands: [{ command: "npm test", exit_code: 0 }], tests: [{ command: "vitest", exit_code: 0 }], guards: [{ name: "clean-code-guard", status: "passed", exit_code: 0 }], known_risks: [], pull_request_title: "Repair validation", pull_request_body: "## Summary\n\nRepairs validation." } })
    if (url.endsWith("/api/tasks/task-1")) return response(tasks[0])
    throw new Error(`Unhandled fetch: ${url}`)
  })
  vi.stubGlobal("fetch", fetchMock)
  return fetchMock
}

async function login() {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "owner@example.com" } })
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct-horse-battery-staple" } })
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }))
  await screen.findByText("Start a repository task")
}

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

describe("MEZO task interface", () => {
  it("submits a real repository task and shows the backend runner offline state", async () => {
    installFetch([])
    render(<App />); await login()
    expect(await screen.findByText("offline · busy").catch(() => screen.findByText("offline"))).toBeTruthy()
    fireEvent.change(screen.getByLabelText("Task title"), { target: { value: "Repair validation" } })
    fireEvent.change(screen.getByLabelText("Development task"), { target: { value: "Fix the failing tests safely" } })
    fireEvent.click(screen.getByRole("button", { name: "Queue task" }))
    await waitFor(() => expect(screen.getAllByText("Repair validation").length).toBeGreaterThan(0))
  })

  it("renders a failed task and its validated unified diff", async () => {
    installFetch([task("failed", { error: "pytest failed", changed_files: [{ path: "a.py", additions: 1, deletions: 0 }], diff_text: "diff --git a/a.py b/a.py\n+safe = True" })])
    render(<App />); await login()
    fireEvent.click(await screen.findByRole("button", { name: /Repair validation/ }))
    expect(await screen.findByText("Task failed")).toBeTruthy()
    expect(screen.getByText("pytest failed")).toBeTruthy()
    expect(screen.getByText(/safe = True/)).toBeTruthy()
  })

  it("renders the exact-diff approval dialog before Draft PR creation", async () => {
    installFetch([task("waiting_for_approval", { approval_state: "pending", diff_hash: "a".repeat(64) })])
    render(<App />); await login()
    fireEvent.click(await screen.findByRole("button", { name: /Repair validation/ }))
    expect(await screen.findByText("Create Draft Pull Request")).toBeTruthy()
    expect(screen.getByRole("button", { name: "Approve exact diff" })).toBeTruthy()
    expect(screen.getByText("1 files, +2 / -1")).toBeTruthy()
    expect(screen.getAllByText("Repair validation").length).toBeGreaterThan(1)
  })
})
