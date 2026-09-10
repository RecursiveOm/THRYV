# V1 deployment preparation

No public deployment is authorized or performed. The V1 foundation and its migration/container definitions are prepared for a small single-host service. The complete live DeepSeek-to-Chrome acceptance gate passed on September 11, 2026. No V2 work is authorized.

## Required hosting layout

Use HTTPS for frontend and API, preferably on the same site (for example `app.example.com` and `api.example.com`) or behind one origin. The cookie is SameSite=Lax; unrelated frontend/API sites are intentionally not supported. Set `FRONTEND_ORIGIN` to the exact frontend HTTPS origin and build Next with `NEXT_PUBLIC_API_URL` set to the API HTTPS origin. Cookies are host-only; keep the API host exclusive to THRYV. Terminate TLS at a trusted proxy and disable header/body/token/query capture. HSTS belongs at that edge.

Set `APP_ENV=production`, a persistent `DATABASE_URL`, and a valid server-only `CREDENTIAL_ENCRYPTION_KEY`. Production startup rejects a missing/invalid encryption key. Do not place it in image layers, source control, frontend env, shell history, or shared database backups. Generate/inject through a protected host secret mechanism. `.env` is for local development and must remain 0600 and ignored.

SQLite is the smallest tested default. Run one backend worker on one host with a persistent private volume. Do not place the SQLite file on a shared network filesystem or ephemeral serverless disk. SQLAlchemy includes an asyncpg driver and portable GUID schema, but a PostgreSQL production deployment is not certified by the local SQLite acceptance tests; run the suite against the intended service before switching.

## Build and migrate

From the repository root:

```bash
docker build -t thryv-backend:v1 backend
```

Optionally verify the local image with `uv run --project backend python backend/scripts/container_smoke.py`; this creates and removes its own disposable volume/container and temporary secret.

The image runs as UID 10001 and includes Alembic migrations. `/data` is a 0700 data directory, and `DATABASE_URL` defaults to `sqlite+aiosqlite:////data/thryv.db`. Provision a private persistent Docker volume or bind directory accessible to UID 10001. Before first start and each schema upgrade, stop the backend/Companions, back up data, and run an explicit migration with the same volume and protected environment:

```bash
docker run --rm --env-file /secure/thryv.env -v thryv-data:/data thryv-backend:v1 alembic upgrade head
```

Then start the server with the same environment and volume, exposing the container only through the intended private reverse-proxy network. The image listens on container port 8000 by default (`PORT` can override it). It does not migrate automatically at startup or bake secrets into the image. `GET /health` tests process liveness only; verify schema/readiness via an authenticated account request after migration.

For Next:

```bash
cd frontend
npm ci
NEXT_TELEMETRY_DISABLED=1 npm run build
npm run start
```

Inject `NEXT_PUBLIC_API_URL` before building. Use your host's secret-safe configuration rather than putting credentials in command lines. Backend concurrency defaults to twenty and provider timeout to sixty seconds; proxy response timeouts must accommodate the 70-second browser deadline. Set request-body limits to at most 150 KB. Apply shared edge rate limits for registration/login/pairing; the backend's direct-client-IP limiter is process-local and does not trust forwarded headers.

## Backups, upgrades, and rollback

Back up SQLite while stopped or use SQLite's consistent backup API. Protect backups like live conversations. Keep the vault key in separately restricted recoverable storage. A database-only backup cannot decrypt credentials; a key-only backup cannot restore conversations. Test restoration before accepting other people's data.

Migrations are versioned in `backend/migrations/versions`. Revision `4f853356ea01` creates users, hashed sessions, conversations/turns, provider ciphertext, pairing, devices, and actions. `675b403091a8` widens activity timestamps for millisecond ordering and PostgreSQL integer safety. Alembic round-trip tests and metadata drift checks cover SQLite. Downgrade removes V1 state at `base`; never do this on production without a separately authorized destructive migration plan. Prefer rollback to a compatible application version, leaving the schema intact.

After restoring an older server or Companion ledger backup, stop existing Companions and revoke/re-pair affected devices. Rolling back execution history can invalidate replay guarantees. Do not manually reset queued/running actions to retry them; create a new user-reviewed request after checking the desktop.

## Remaining production decisions

Account recovery/email verification/MFA, per-account storage quotas, retention/deletion policy and backup erasure, distributed abuse limits, observability without secrets, and disaster recovery are not built in V1. No public rollout or meaningful paid infrastructure should be inferred from the local foundation. Companion has no signed installer/auto-updater or background service yet and supports practical Linux X11/XWayland launching only.
