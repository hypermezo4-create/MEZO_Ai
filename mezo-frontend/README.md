# MEZO web and desktop client

The React/Vite client is a remote development-agent interface for `mezo-api`. It does not run a local model or spawn a local backend sidecar. The Tauri wrapper builds the same remote client without local-machine shell authority.

```bash
npm ci
npm run dev --workspace=mezo-frontend
npm run typecheck --workspace=mezo-frontend
npm run test --workspace=mezo-frontend -- --run
npm run build --workspace=mezo-frontend
```

Set `VITE_MEZO_API_URL` at build time only when the API is on a different origin. The production API image serves the built app on the same origin. Authentication tokens are kept in memory, and the UI displays only data returned by authenticated API routes and SSE.
