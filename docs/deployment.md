# Deployment preparation — THRYV V0

These are preparation instructions. Do not publish a public production URL until Omkar explicitly authorizes deployment.

## Frontend

The `frontend` directory is a standard Next.js app, suitable for Vercel or a Node-capable host. Set the host's project root to `frontend`, Node version to 24, install command to `npm ci`, and build command to `npm run build`.

Set `NEXT_PUBLIC_API_URL=https://api.example.com` **before building**. This is a public origin, never a key. Rebuild after changing it. For a Node host, use `npm run start -- --hostname 0.0.0.0 --port 3000`. The app uses no host-specific business APIs. Preserve the security headers from `next.config.ts`, and terminate HTTPS at the hosting edge.

## Backend

Build from the backend directory:

```bash
docker build -t thryv-backend ./backend
```

The image uses Python 3.12, locked production dependencies, a non-root runtime user, a health check, and no credentials or tests. Host settings:

```text
APP_ENV=production
FRONTEND_ORIGIN=https://app.example.com
DEEPSEEK_MODEL=deepseek-flash
LOG_LEVEL=INFO
PROVIDER_TIMEOUT_SECONDS=60
MAX_CONCURRENT_REQUESTS=20
PORT=8000
```

Use the platform's HTTPS ingress. Do not expose plain HTTP port 8000 directly to the public internet. Configure readiness against `/health`, a proxy response timeout above 60 seconds, a body limit near 150 KB, a header limit, and edge per-client rate/connection limits. Turn off request-body capture and redact Authorization. Do not trust arbitrary forwarded headers; configure trusted proxies at the host only when needed.

For a container test on loopback only:

```bash
docker run --rm -p 127.0.0.1:8000:8000 \
  -e APP_ENV=development \
  -e FRONTEND_ORIGIN=http://localhost:3000 \
  thryv-backend
```

An ordinary Python host can instead run `uv sync --locked --no-dev` and `uv run uvicorn app.main:app --host 0.0.0.0 --port 8000 --no-access-log`, behind its HTTPS ingress. The app doesn't need a database, mounted volume or developer DeepSeek key.

## Release checks after deployment authorization

1. Run backend tests/format/lint, frontend lint/typecheck/build/browser tests and dependency audits.
2. Verify both production origins use HTTPS, CORS allows only the frontend origin, and API docs are disabled.
3. Check health, BYOK connection, one identity reply, one contextual follow-up, invalid key, network failure and mobile layout.
4. Confirm keys never enter URLs, response/error logs, request capture, telemetry or caches.
5. Confirm the hosting edge enforces rate, size and connection limits; a user key does not authenticate a THRYV account.
6. Record the deployed commit and inspect service startup/health without logging secrets.

No paid hosting plan, public deployment, cloud infrastructure, authentication or persistent data store is created by V0. Evaluate these only in the approved next milestone.
