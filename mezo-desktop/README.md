# MEZO desktop client

This Tauri v2 shell packages the same React interface as the web application. It is a remote client for the Fly-hosted `mezo-api`; it has no shell, filesystem, local model, sidecar, or unrestricted machine-control permission.

Set `VITE_MEZO_API_URL` to the deployed HTTPS API before a release build. The content security policy permits HTTPS API connections and local Vite during development.

```bash
npm ci
npm run build:web
npm run build:desktop
```

Rust-only checks:

```bash
cargo fmt --manifest-path mezo-desktop/src-tauri/Cargo.toml --check
cargo check --manifest-path mezo-desktop/src-tauri/Cargo.toml
```
