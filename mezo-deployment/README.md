# mezo-deployment

مستودع إعدادات وسكريبتات النشر لمنصة **MEZO Local AI Platform**.

> [!IMPORTANT]
> **Fly.io Deployment Architecture & GPU Deprecation Notice**:
> Fly.io hosts orchestration and the Gemini fallback path (`mezo-backend`, `mezo-control-plane`, `mezo-skills-manager`, static frontend).
> Heavy local-model inference runs on the user's own machine because Fly no longer offers GPU Machines as of July 31, 2026.

## Fly.io Scale-To-Zero CPU Deployments

كل خدمة تمتلك ملف `fly.toml` منفصل مع تفعيل الحجم التلقائي والتوقف عند الخمول (`auto_stop_machines = true`, `auto_start_machines = true`):

- **Backend**: `fly/fly-backend.toml`
- **Control Plane**: `fly/fly-control-plane.toml`
- **Skills Manager**: `fly/fly-skills-manager.toml`

### إدارة الأسرار (Fly Secrets):
يتم ضبط المفاتيح السرية عبر Fly CLI دون تضمين أي أسرار في السورس كود:
```bash
fly secrets set GEMINI_API_KEY="your_api_key" JWT_SECRET="your_jwt_secret" -a mezo-backend
```

## Vercel Web Deployment

MEZO AI utilizes Vercel solely for hosting the static React SPA frontend. All stateful connections, including WebSockets/SSE for token streaming, remain on the Fly.io backend because of Vercel's serverless function execution time limits.

- **Vercel Preview Deployments**: Per-PR preview URLs (`https://mezo-ai-*.vercel.app`) dynamically talk to the staging Fly backend. They are enabled dynamically in the backend CORS configuration.
- **Production Domain**: The static production frontend uses `VITE_API_BASE_URL` to route requests to the Fly production backend.

## التشغيل المحلي عبر Docker Compose
```bash
docker-compose -f docker/docker-compose.yml up -d
```
