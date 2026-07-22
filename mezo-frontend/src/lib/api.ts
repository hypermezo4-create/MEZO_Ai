export type Mode = "auto" | "fast" | "coding" | "deep" | "vision" | "multi"
export interface Project { id: string; name: string; repository_url: string; default_branch: string }
export interface Conversation { id: string; title: string; created_at: string; updated_at: string }
export interface Message { id: number; role: "user" | "assistant" | "system" | "tool"; content: string; created_at: string }
export interface ChangedFile { path: string; status?: string }
export interface Task {
  id: string; conversation_id: string; project_id: string; prompt: string; mode: Mode; status: string;
  changed_files: ChangedFile[]; diff_text: string; error: string | null; decision: string | null;
  reviewer_chain: string[]; created_at: string; runner_id: string | null;
}
export interface Machine { slot_id: string; machine_id: string | null; role: string; app: string; region: string; size: string; memory_mb: number; status: string }
export interface ClusterStatus {
  api: string; database: string; valkey: string; github_configured: boolean; machines: Machine[];
  router: { healthy: boolean; models?: Record<string, { healthy: boolean; latency_ms?: number }> };
}
export interface TaskEvent { id: number; event_type: string; payload: Record<string, unknown>; created_at: string }

class Client {
  private async request<T>(path: string, options?: RequestInit): Promise<T> {
    const response = await fetch(path, { ...options, headers: { "Content-Type": "application/json", ...options?.headers } })
    if (!response.ok) {
      let message = `${response.status} ${response.statusText}`
      try { message = (await response.json()).detail || message } catch { /* not JSON */ }
      throw new Error(message)
    }
    return response.json() as Promise<T>
  }
  status = () => this.request<ClusterStatus>("/api/status")
  projects = () => this.request<Project[]>("/api/projects")
  createProject = (input: { name: string; repository_url: string; default_branch: string }) => this.request<Project>("/api/projects", { method: "POST", body: JSON.stringify(input) })
  conversations = () => this.request<Conversation[]>("/api/conversations")
  messages = (id: string) => this.request<Message[]>(`/api/conversations/${id}/messages`)
  tasks = () => this.request<Task[]>("/api/tasks")
  task = (id: string) => this.request<Task>(`/api/tasks/${id}`)
  createTask = (input: { project_id: string; prompt: string; conversation_id?: string; mode: Mode }) => this.request<Task>("/api/tasks", { method: "POST", body: JSON.stringify(input) })
  cancel = (id: string) => this.request<Task>(`/api/tasks/${id}/cancel`, { method: "POST" })
  decide = (id: string, value: "accept" | "reject") => this.request<Task>(`/api/tasks/${id}/decision?value=${value}`, { method: "POST" })
  stream(id: string, after: number, signal: AbortSignal, onEvent: (event: TaskEvent) => void) {
    return fetch(`/api/tasks/${id}/events?after=${after}`, { signal }).then(async response => {
      if (!response.ok || !response.body) throw new Error(`Stream failed: HTTP ${response.status}`)
      const reader = response.body.getReader(); const decoder = new TextDecoder(); let buffer = ""
      while (true) {
        const { value, done } = await reader.read(); buffer += decoder.decode(value, { stream: !done })
        const frames = buffer.split(/\r?\n\r?\n/); buffer = frames.pop() || ""
        for (const frame of frames) {
          const line = frame.split(/\r?\n/).find(item => item.startsWith("data: "))
          if (line) onEvent(JSON.parse(line.slice(6)) as TaskEvent)
        }
        if (done) return
      }
    })
  }
}
export const api = new Client()
