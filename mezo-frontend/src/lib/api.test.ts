import { afterEach, describe, expect, it, vi } from "vitest"
import { api } from "./api"

afterEach(() => {
  vi.unstubAllGlobals()
})

describe("cluster API", () => {
  it("does not send a MEZO login token", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify([]), { status: 200 }))
    vi.stubGlobal("fetch", fetchMock)
    await api.projects()
    const headers = fetchMock.mock.calls[0][1]?.headers as Record<string, string>
    expect(headers.Authorization).toBeUndefined()
  })

  it("reports an inactive development proxy instead of parsing HTML as JSON", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("<!doctype html><html></html>", {
      status: 200,
      headers: { "Content-Type": "text/html" },
    })))

    await expect(api.status()).rejects.toThrow("MEZO API proxy is not active")
  })

  it("parses streamed runner events once even when a frame is repeated", async () => {
    const frame = 'id: 1\ndata: {"id":1,"event_type":"stdout","payload":{"message":"ok"},"created_at":"now"}\n\n'
    const body = new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(frame + frame))
        controller.close()
      },
    })
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(body, {
      status: 200,
      headers: { "Content-Type": "text/event-stream" },
    })))
    const events: unknown[] = []
    await api.stream("task", 0, new AbortController().signal, event => events.push(event))
    expect(events).toHaveLength(1)
  })
})
