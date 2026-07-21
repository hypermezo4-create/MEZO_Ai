import { describe, expect, it, vi } from "vitest"
import { MezoApi } from "./api"


describe("MezoApi", () => {
  it("sends the verified bearer token and preserves real runner data without fallback values", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([
      { id: "runner-1", name: "fly-1", status: "offline", version: "1", current_task_id: null, last_heartbeat_at: "2026-01-01", disk_total_bytes: null, disk_free_bytes: null, capabilities: {} },
    ]), { status: 200, headers: { "Content-Type": "application/json" } }))
    vi.stubGlobal("fetch", fetchMock)
    const api = new MezoApi("https://mezo.example")
    api.setToken("verified-token")
    const runners = await api.runners()
    expect(runners[0].status).toBe("offline")
    expect(runners[0].disk_total_bytes).toBeNull()
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer verified-token")
  })

  it("renders task SSE frames as structured events", async () => {
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode('id: 4\nevent: stdout\ndata: {"id":4,"type":"stdout","stream":"stdout","timestamp":"2026-01-01T00:00:00Z","payload":{"message":"tests passed"}}\n\n'))
        controller.close()
      },
    })
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { status: 200 })))
    const api = new MezoApi()
    api.setToken("token")
    const events: unknown[] = []
    await api.streamTask("task-1", 0, new AbortController().signal, event => events.push(event))
    expect(events).toHaveLength(1)
    expect((events[0] as { payload: { message: string } }).payload.message).toBe("tests passed")
  })
})
