import { describe, expect, it, vi } from "vitest"
import { api } from "./api"

describe("cluster API", () => {
  it("does not send a MEZO login token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }))
    vi.stubGlobal("fetch", fetchMock)
    await api.projects()
    const headers = fetchMock.mock.calls[0][1]?.headers as Record<string, string>
    expect(headers.Authorization).toBeUndefined()
  })

  it("parses streamed runner events", async () => {
    const body = new ReadableStream({ start(controller) { controller.enqueue(new TextEncoder().encode('id: 1\ndata: {"id":1,"event_type":"stdout","payload":{"message":"ok"},"created_at":"now"}\n\n')); controller.close() } })
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, { status: 200 })))
    const events: unknown[] = []
    await api.stream("task", 0, new AbortController().signal, event => events.push(event))
    expect(events).toHaveLength(1)
  })
})
