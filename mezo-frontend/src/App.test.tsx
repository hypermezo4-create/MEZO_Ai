import { cleanup, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"
import App from "./App"

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it("opens directly into the private workspace with no login or bootstrap", async () => {
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    const value = url.endsWith("/api/status")
      ? { api: "ok", database: "postgres", valkey: "ok", github_configured: false, machines: [], router: { healthy: true, models: {} } }
      : []
    return Promise.resolve(new Response(JSON.stringify(value), { status: 200, headers: { "Content-Type": "application/json" } }))
  }))
  render(<App />)
  expect(await screen.findByText("What should MEZO build?")).toBeTruthy()
  expect(screen.queryByText(/sign in|password|bootstrap/i)).toBeNull()
  expect(screen.getByLabelText("Repository URL")).toBeTruthy()
})
