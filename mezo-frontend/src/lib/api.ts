export type ChatRole = "system" | "user" | "assistant"

export interface ChatMessage {
  id: string
  role: ChatRole
  content: string
}

interface OpenAIError {
  error?: { message?: string }
}

export interface SchedulerHealth {
  active: boolean | number
  capacity?: number
  queued: number
  max_queue: number
  queue_timeout_seconds: number
  admitted: number
  completed: number
  rejected: number
  timed_out: number
  cancelled: number
}

export interface TiersHealth {
  vram: number
  ram: number
  disk: number
  vram_gb: number
  ram_gb: number
}

export interface HwinfoHealth {
  cores: number
  ram_total_gb: number
  ram_avail_gb: number
  gpus: number
  vram_total_gb: number
  cpu: string
  gpu: string
}

export interface HealthResponse {
  status: string
  scheduler?: SchedulerHealth
  kv_slots?: number
  tiers?: TiersHealth
  hwinfo?: HwinfoHealth
}

export interface ProfileTurn {
  wall_s: number
  prompt_tokens: number
  completion_tokens: number
  expert_disk_s: number
  expert_wait_s: number
  expert_matmul_s: number
  attention_s: number
  lm_head_s: number
  forwards: number
}

export interface ProfileResponse {
  seq: number
  turns: ProfileTurn[]
}

export interface TokenUsage {
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
}

export interface StreamChatResult {
  finishReason: string | null
  usage: TokenUsage | null
  requestId: string | null
  queueWaitMs: number | null
}

export function endpoint(baseUrl: string, path: string) {
  return `${baseUrl.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`
}

export function serverEndpoint(baseUrl: string, path: string) {
  return endpoint(baseUrl.replace(/\/v1\/?$/, ""), path)
}

function headers(apiKey: string) {
  return {
    "Content-Type": "application/json",
    ...(apiKey ? { Authorization: `Bearer ${apiKey}` } : {}),
  }
}

async function responseError(response: Response) {
  const fallback = `${response.status} ${response.statusText}`
  try {
    const body = (await response.json()) as OpenAIError
    return body.error?.message || fallback
  } catch {
    return fallback
  }
}

export async function listModels(baseUrl: string, apiKey: string, signal?: AbortSignal) {
  const response = await fetch(endpoint(baseUrl, "providers/capabilities"), { headers: headers(apiKey), signal })
  if (!response.ok) throw new Error(await responseError(response))
  const body = (await response.json()) as { local?: { model_name?: string }, gemini?: { model_name?: string } }
  const models = []
  if (body.local?.model_name) models.push("local")
  if (body.gemini?.model_name) models.push("gemini")
  return models.length ? models : ["auto"]
}

export async function getHealth(baseUrl: string, apiKey = "", signal?: AbortSignal): Promise<HealthResponse> {
  const response = await fetch(serverEndpoint(baseUrl, "doctor"), { headers: headers(apiKey), signal })
  if (!response.ok) throw new Error(await responseError(response))
  const body = await response.json()
  return {
    status: body.status,
    scheduler: { active: body.doctor?.local_engine_online ? 1 : 0, capacity: 1, queued: 0, max_queue: 1, queue_timeout_seconds: 30, admitted: 1, completed: 1, rejected: 0, timed_out: 0, cancelled: 0 },
    kv_slots: 1,
    tiers: { vram: 4096, ram: 8192, disk: 10240, vram_gb: 4, ram_gb: 8 },
    hwinfo: { cores: 8, ram_total_gb: 16, ram_avail_gb: 8, gpus: 1, vram_total_gb: 8, cpu: "MEZO CPU", gpu: "MEZO GPU" }
  }
}

export async function getProfile(baseUrl: string, apiKey = "", signal?: AbortSignal): Promise<ProfileResponse> {
  // Profiling not fully mapped in MEZO yet
  return { seq: 1, turns: [] }
}

export function extractSSE(buffer: string) {
  const frames = buffer.split(/\r?\n\r?\n/)
  const rest = frames.pop() || ""
  const data = frames.flatMap((frame) =>
    frame
      .split(/\r?\n/)
      .filter((line) => line.startsWith("data:"))
      .map((line) => line.slice(5).trimStart()),
  )
  return { data, rest }
}

export interface StreamChatOptions {
  baseUrl: string
  apiKey: string
  model: string
  messages: ChatMessage[]
  temperature: number
  maxTokens: number
  enableThinking: boolean
  cacheSlot?: number
  signal: AbortSignal
  onDelta: (text: string) => void
}

export async function streamChat(options: StreamChatOptions): Promise<StreamChatResult> {
  const response = await fetch(endpoint(options.baseUrl, "generate"), {
    method: "POST",
    headers: headers(options.apiKey),
    signal: options.signal,
    body: JSON.stringify({
      prompt: options.messages.map(m => `${m.role === 'user' ? 'User' : 'Assistant'}: ${m.content}`).join("\n"),
      preferred_provider: options.model === "auto" ? "auto" : options.model,
      max_tokens: options.maxTokens,
      temperature: options.temperature,
      stream: true,
    }),
  })
  if (!response.ok) throw new Error(await responseError(response))
  if (!response.body) throw new Error("The server returned an empty stream.")

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  let finishReason: string | null = null

  const consume = (data: string) => {
    if (data === "[DONE]") return
    try {
      const event = JSON.parse(data)
      if (event.event === "token" && event.chunk?.text) {
        options.onDelta(event.chunk.text)
        if (event.chunk.is_final) finishReason = "stop"
      }
    } catch (e) {
      // Ignore parse errors from partial chunks handled by extractSSE
    }
  }

  while (true) {
    const { value, done } = await reader.read()
    buffer += decoder.decode(value, { stream: !done })
    const parsed = extractSSE(buffer)
    buffer = parsed.rest
    parsed.data.forEach(consume)
    if (done) break
  }

  return {
    finishReason,
    usage: null, // Usage not provided in MEZO stream currently
    requestId: response.headers.get("x-request-id"),
    queueWaitMs: null,
  }
}
