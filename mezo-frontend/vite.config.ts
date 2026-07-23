import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

const apiTarget = process.env.MEZO_DEV_API || "http://127.0.0.1:8787"
const tunnelMessage = "MEZO local API tunnel is not running on 127.0.0.1:8787. Start fly proxy, then refresh this page."

function proxyOptions() {
  return {
    target: apiTarget,
    changeOrigin: false,
    configure(proxy: { on: (event: string, handler: (...args: any[]) => void) => void }) {
      proxy.on("error", (_error, _request, response) => {
        if (!response || response.headersSent) return
        response.writeHead(503, { "Content-Type": "application/json; charset=utf-8" })
        response.end(JSON.stringify({ detail: tunnelMessage }))
      })
    },
  }
}

export default defineConfig({
  plugins: [react()],
  server: {
    host: "127.0.0.1",
    port: 3000,
    strictPort: true,
    open: false,
    headers: {
      "Cache-Control": "no-store",
    },
    proxy: {
      "/api": proxyOptions(),
      "/healthz": proxyOptions(),
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
  },
})
