import { defineConfig } from "vite"
import react from "@vitejs/plugin-react"

const apiTarget = process.env.MEZO_DEV_API || "http://127.0.0.1:8787"

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
      "/api": {
        target: apiTarget,
        changeOrigin: false,
      },
      "/healthz": {
        target: apiTarget,
        changeOrigin: false,
      },
    },
  },
  preview: {
    host: "127.0.0.1",
    port: 4173,
    strictPort: true,
  },
})
