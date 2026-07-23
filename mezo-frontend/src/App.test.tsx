import { cleanup, fireEvent, render, screen } from "@testing-library/react"
import { afterEach, expect, it, vi } from "vitest"

import App from "./App"

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function mockWorkspace() {
  vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
    const url = String(input)
    const value = url.endsWith("/api/status")
      ? {
          api: "ok",
          database: "postgres",
          valkey: "ok",
          github_configured: false,
          configured_machine_count: 9,
          max_machine_count: 20,
          max_concurrent_tasks: 4,
          machines: [],
          router: { healthy: true, models: {} },
        }
      : []
    return Promise.resolve(new Response(JSON.stringify(value), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    }))
  }))
}

it("opens directly into the MEZO workspace with no login", async () => {
  mockWorkspace()
  render(<App />)

  expect(await screen.findByText("What should MEZO build?")).toBeTruthy()
  expect(screen.queryByText(/sign in|password|bootstrap/i)).toBeNull()
  expect(screen.getByRole("button", { name: "New chat" })).toBeTruthy()
  expect(screen.getByLabelText("MEZO mode")).toBeTruthy()
})

it("reveals a repository form from the projects section", async () => {
  mockWorkspace()
  render(<App />)

  await screen.findByText("What should MEZO build?")
  fireEvent.click(screen.getByRole("button", { name: "Add project" }))
  expect(screen.getByLabelText("Repository URL")).toBeTruthy()
  expect(screen.getByText("Default branch")).toBeTruthy()
})
