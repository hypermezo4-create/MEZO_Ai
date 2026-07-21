# MEZO AI — Platform Parity Matrix

This document tracks feature parity across all supported platforms (Web, Desktop, Mobile). It is the single source of truth for the cross-platform expansion.

| Feature Area | Web (React/Vercel) | Desktop (Tauri/.exe) | Mobile (Flutter/.apk) |
|---|---|---|---|
| **Core Connection** |
| Auth / Token Storage | ✅ Done (localStorage) | ✅ Done (localStorage via Web) | ✅ Done (Secure Storage) |
| Fly.io Backend API | ✅ Done | ✅ Done | ✅ Done |
| SSE Streaming | ✅ Done | ✅ Done | ✅ Done (Dart Client) |
| **User Interface** |
| Design Tokens Implemented | ✅ Done | ✅ Done | 🟡 Partial |
| Provider Indicator (Local/Gemini) | ✅ Done | ✅ Done | ✅ Done |
| Chat View & Artifacts | ✅ Done | ✅ Done | 🟡 MVP (Chat Only) |
| **Control Plane** |
| Workflow Panel (Live Steps) | ✅ Done | ✅ Done | ❌ Not Yet |
| Tier-3 Confirmation Dialog | ✅ Done | ✅ Done | ❌ Not Yet |
| Memory Panel (Fact Mgmt) | ✅ Done | ✅ Done | ❌ Not Yet |
| Kill Switch Status (Read) | ✅ Done | ✅ Done (Tray Tooltip) | ✅ Done |
| Kill Switch Toggle (Arm/Disarm) | ✅ Done | ✅ Done | ❌ Not Yet |
| **System Integrations** |
| Native File System Access | ❌ N/A (Sandboxed) | 🟡 Planned (Tauri Commands)| ❌ N/A |
| Push Notifications / Alerts | ❌ N/A | ❌ Not Yet | ❌ Not Yet |

## Legend
- ✅ **Done**: Implemented, tested, and compliant with contract fixtures.
- 🟡 **Partial / MVP**: Initial implementation complete, full parity pending.
- ❌ **Not Yet**: Not started.
