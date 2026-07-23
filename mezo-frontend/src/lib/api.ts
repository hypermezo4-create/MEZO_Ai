export type Mode = "auto" | "fast" | "coding" | "deep" | "vision" | "multi"
export type Interaction = "auto" | "chat" | "agent"

export interface Project {
  id: string
  name: string
  repository_url: string
  default_branch: string
}

export interface Conversation {
  id: string
  title: string
  created_at: string
  updated_at: string
}

export interface Message {
  id: number
  role: "user" | "assistant" | "system" | "tool"
  content: string
  created_at: string
}

export interface ChangedFile {
  path: string
  status?: string
}

export interface Task {
  id: string
  conversation_id: string
  project_id: string
  prompt: string
  mode: Mode
  status: string
  changed_files: ChangedFile[]
  diff_text: string
  error: string | null
  decision: string | null
  reviewer_chain: string[]
  created_at: string
  started_at?: string | null
  finished_at?: string | null
  runner_id: string | null
}

export interface DispatchResult {
  kind: "chat" | "agent"
  interaction: "chat" | "agent"
  conversation_id: string
  message: Message
  task: Task | null
}

export interface Machine {
  slot_id: string
  machine_id: string | null
  role: string
  app: string
  region: string
  size: string
  memory_mb: number
  status: string
  metadata?: Record<string, unknown>
  last_heartbeat_at?: string
}

export interface ModelReplica {
  endpoint: string
  healthy: boolean
  error?: string
}

export interface ModelHealth {
  healthy: boolean
  configured?: boolean
  label?: string
  purpose?: string
  latency_ms?: number
  circuit_open?: boolean
  replicas?: ModelReplica[]
}

export interface ClusterStatus {
  api: string
  database: string
  valkey: string
  github_configured: boolean
  configured_machine_count?: number
  max_machine_count?: number
  max_concurrent_tasks?: number
  machines: Machine[]
  router: {
    healthy: boolean
    models?: Record<string, ModelHealth>
  }
}

export interface TaskEvent {
  id: number
  event_type: string
  payload: Record<string, unknown>
  created_at: string
}

class Client {
  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const response = await fetch(path, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        ...options?.headers,
      },
    })

    if (!response.ok) {
      const fallback = `${response.status} ${response.statusText}`.trim()
      const payload = await response.json().catch(() => ({ detail: fallback })) as { detail?: string }
      throw new Error(payload.detail || fallback || "MEZO request failed")
    }

    if (response.status === 204) return undefined as T
    return response.json() as Promise<T>
  }

  status = () => this.request<ClusterStatus>("/api/status")
  projects = () => this.request<Project[]>("/api/projects")
  createProject = (input: { name: string; repository_url: string; default_branch: string }) =>
    this.request<Project>("/api/projects", { method: "POST", body: JSON.stringify(input) })
  conversations = () => this.request<Conversation[]>("/api/conversations")
  createConversation = (title = "New conversation") =>
    this.request<Conversation>("/api/conversations", { method: "POST", body: JSON.stringify({ title }) })
  messages = (id: string) => this.request<Message[]>(`/api/conversations/${id}/messages`)
  dispatch = (input: { prompt: string; conversation_id?: string; project_id?: string; interaction?: Interaction; mode: Mode }) =>
    this.request<DispatchResult>("/api/dispatch", { method: "POST", body: JSON.stringify(input) })
  tasks = () => this.request<Task[]>("/api/tasks")
  task = (id: string) => this.request<Task>(`/api/tasks/${id}`)
  cancel = (id: string) => this.request<Task>(`/api/tasks/${id}/cancel`, { method: "POST" })
  decide = (id: string, value: "accept" | "reject") =>
    this.request<Task>(`/api/tasks/${id}/decision?value=${value}`, { method: "POST" })
  patchUrl = (id: string) => `/api/tasks/${id}/patch`
  archiveUrl = (id: string) => `/api/tasks/${id}/archive`

  async stream(id: string, after: number, signal: AbortSignal, onEvent: (event: TaskEvent) => void): Promise<void> {
    const response = await fetch(`/api/tasks/${id}/events?after=${after}`, { signal })
    const reader = response.body?.getReader()
    if (!response.ok || !reader) throw new Error(`Stream failed: HTTP ${response.status}`)

    const decoder = new TextDecoder()
    const emitted = new Set<number>()
    let buffer = ""

    const emitFrame = (frame: string) => {
      const line = frame.split(/\r?\n/).find(item => item.startsWith("data: "))
      if (!line) return
      try {
        const event = JSON.parse(line.slice(6)) as TaskEvent
        if (!event.id || event.id <= after || emitted.has(event.id)) return
        emitted.add(event.id)
        onEvent(event)
      } catch {
        // Ignore one malformed frame without dropping the live stream.
      }
    }

    while (true) {
      const { value, done } = await reader.read()
      buffer += decoder.decode(value, { stream: !done })
      const frames = buffer.split(/\r?\n\r?\n/)
      buffer = frames.pop() || ""
      frames.forEach(emitFrame)

      if (done) {
        if (buffer.trim()) emitFrame(buffer)
        return
      }
    }
  }
}

export const api = new Client()
