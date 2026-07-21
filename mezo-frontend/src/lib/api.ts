export interface Repository { id: string; full_name: string; default_branch: string; active: boolean }
export interface Project { id: string; name: string; repository_id: string; owner_id: string }
export interface Runner { id: string; name: string; status: string; version: string; current_task_id: string | null; last_heartbeat_at: string; disk_total_bytes: number | null; disk_free_bytes: number | null; capabilities: Record<string, unknown> }
export interface TaskStep { id: string; step_index: number; name: string; description: string; status: string; started_at: string | null; finished_at: string | null; command: string | null; exit_code: number | null; result_summary: string | null; error: string | null; requires_approval: boolean }
export interface Task {
  id: string; user_id: string; repository: string; base_branch: string; working_branch: string; title: string;
  description: string; status: string; current_step: string | null; created_at: string; started_at: string | null;
  finished_at: string | null; runner_id: string | null; workspace_id: string | null; error: string | null;
  approval_state: string; pull_request_url: string | null; changed_files: ChangedFile[]; diff_text: string | null;
  diff_hash: string | null; validation_report: ValidationReport; steps: TaskStep[];
}
export interface ChangedFile { path: string; additions: number | null; deletions: number | null }
export interface ValidationItem { command?: string; name?: string; status?: string; exit_code: number; duration_ms?: number; summary?: string; phase?: string }
export interface ValidationReport { commands?: ValidationItem[]; tests?: ValidationItem[]; guards?: ValidationItem[]; known_risks?: string[]; diff_summary?: { files: number; additions: number; deletions: number } }
export interface ApprovalRequest {
  repository: string
  base_branch: string
  working_branch: string
  changed_files: ChangedFile[]
  diff_hash: string
  commit_sha: string
  diff_summary: { files: number; additions: number; deletions: number }
  commands: ValidationItem[]
  tests: ValidationItem[]
  guards: ValidationItem[]
  known_risks: string[]
  pull_request_title: string
  pull_request_body: string
}
export interface Approval { id: string; task_id: string; diff_hash: string; action: string; state: string; expires_at: string; request: ApprovalRequest }
export interface TaskEvent { id: number; type: string; stream: string | null; timestamp: string; payload: Record<string, unknown> }

type Method = "GET" | "POST" | "PUT" | "DELETE"

export class MezoApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message)
    this.name = "MezoApiError"
  }
}

export class MezoApi {
  readonly baseUrl: string
  private token = ""

  constructor(baseUrl = import.meta.env.VITE_MEZO_API_URL || "") {
    this.baseUrl = baseUrl.replace(/\/$/, "")
  }

  setToken(token: string) { this.token = token }

  private async request<T>(path: string, method: Method = "GET", body?: unknown, extraHeaders?: Record<string, string>): Promise<T> {
    const response = await fetch(`${this.baseUrl}${path}`, {
      method,
      headers: {
        "Content-Type": "application/json",
        ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}),
        ...extraHeaders,
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    if (!response.ok) {
      let message = `${response.status} ${response.statusText}`
      try { message = (await response.json()).detail || message } catch { /* response was not JSON */ }
      throw new MezoApiError(message, response.status)
    }
    return response.json() as Promise<T>
  }

  async login(email: string, password: string) {
    const result = await this.request<{ access_token: string; expires_in: number }>("/api/auth/login", "POST", { email, password })
    this.setToken(result.access_token)
    return result
  }

  async bootstrap(email: string, password: string, bootstrapToken: string) {
    const result = await this.request<{ access_token: string; expires_in: number }>(
      "/api/auth/bootstrap", "POST", { email, password }, { "X-MEZO-Bootstrap-Token": bootstrapToken },
    )
    this.setToken(result.access_token)
    return result
  }

  repositories = () => this.request<Repository[]>("/api/repositories")
  projects = () => this.request<Project[]>("/api/projects")
  tasks = () => this.request<Task[]>("/api/tasks")
  task = (id: string) => this.request<Task>(`/api/tasks/${id}`)
  runners = () => this.request<Runner[]>("/api/runners")
  audit = (taskId?: string) => this.request<{ integrity_valid: boolean; records: unknown[] }>(`/api/audit${taskId ? `?task_id=${encodeURIComponent(taskId)}` : ""}`)
  cancelTask = (id: string) => this.request<Task>(`/api/tasks/${id}/cancel`, "POST")
  approval = (id: string) => this.request<Approval>(`/api/tasks/${id}/approval`)
  decideApproval = (id: string, decision: "approve" | "reject") => this.request<{ state: string; diff_hash: string }>(`/api/tasks/${id}/approval`, "POST", { decision })
  createDraftPullRequest = (id: string) => this.request<{ status: string }>(`/api/tasks/${id}/pull-request`, "POST")

  createTask(input: { repository_id: string; project_id?: string; base_branch?: string; title: string; description: string }) {
    return this.request<Task>("/api/tasks", "POST", input)
  }

  async streamTask(id: string, after: number, signal: AbortSignal, onEvent: (event: TaskEvent) => void): Promise<void> {
    const response = await fetch(`${this.baseUrl}/api/tasks/${id}/events?after=${after}`, {
      headers: { Authorization: `Bearer ${this.token}` },
      signal,
    })
    if (!response.ok || !response.body) throw new Error(`Task stream failed with HTTP ${response.status}`)
    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ""
    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      const frames = buffer.split(/\r?\n\r?\n/)
      buffer = frames.pop() || ""
      for (const frame of frames) {
        const line = frame.split(/\r?\n/).find((item) => item.startsWith("data: "))
        if (!line) continue
        try {
          const parsed = JSON.parse(line.slice(6))
          if (parsed.id) onEvent(parsed as TaskEvent)
        } catch { /* malformed server event is ignored; the stream remains live */ }
      }
      if (done) return
    }
  }
}
