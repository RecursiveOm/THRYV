# V3 deployment preparation

No public deployment is authorized or performed. The existing foundation is prepared for a small single-host service. V2 adds explicit memory, optional local speech and off-by-default Beta wake listening. V3 adds isolated public research and confirmed local website opening; see the current verification report for live acceptance.

## Required hosting layout

Use HTTPS for frontend and API, preferably on the same site (for example `app.example.com` and `api.example.com`) or behind one origin. The cookie is SameSite=Lax; unrelated frontend/API sites are intentionally not supported. Set `FRONTEND_ORIGIN` to the exact frontend HTTPS origin and build Next with `NEXT_PUBLIC_API_URL` set to the API HTTPS origin. Cookies are host-only; keep the API host exclusive to THRYV. Terminate TLS at a trusted proxy and disable header/body/token/query capture. HSTS belongs at that edge.

Set `APP_ENV=production`, a persistent `DATABASE_URL`, and a valid server-only `CREDENTIAL_ENCRYPTION_KEY`. Production startup rejects a missing/invalid encryption key. Do not place it in image layers, source control, frontend env, shell history, or shared database backups. Generate/inject through a protected host secret mechanism. `.env` is for local development and must remain 0600 and ignored.

SQLite is the smallest tested default. Run one backend worker on one host with a persistent private volume. Do not place the SQLite file on a shared network filesystem or ephemeral serverless disk. SQLAlchemy includes an asyncpg driver and portable GUID schema, but a PostgreSQL production deployment is not certified by the local SQLite acceptance tests; run the suite against the intended service before switching.

## Build and migrate

From the repository root:

```bash
docker build -t thryv-backend:v3 backend
```

Optionally verify the local image with `uv run --project backend python backend/scripts/container_smoke.py`; this creates and removes its own disposable volume/container and temporary secret.

The image runs as UID 10001 and includes Alembic migrations. `/data` is a 0700 data directory, and `DATABASE_URL` defaults to `sqlite+aiosqlite:////data/thryv.db`. Provision a private persistent Docker volume or bind directory accessible to UID 10001. Before first start and each schema upgrade, stop the backend/Companions, back up data, and run an explicit migration with the same volume and protected environment:

```bash
docker run --rm --env-file /secure/thryv.env -v thryv-data:/data thryv-backend:v3 alembic upgrade head
```

Then start the server with the same environment and volume, exposing the container only through the intended private reverse-proxy network. The image listens on container port 8000 by default (`PORT` can override it). It does not migrate automatically at startup or bake secrets into the image. `GET /health` tests process liveness only; verify schema/readiness via an authenticated account request after migration.

For Next:

```bash
cd frontend
npm ci
NEXT_TELEMETRY_DISABLED=1 npm run build
npm run start
```

Inject `NEXT_PUBLIC_API_URL` before building. Use your host's secret-safe configuration rather than putting credentials in command lines. Backend concurrency defaults to twenty and provider timeout to sixty seconds; proxy response timeouts must accommodate the 70-second browser deadline. Allow up to 960,044 bytes for `/api/voice/transcribe` and `/api/voice/wake`; keep other request-body limits at 150 KB. Apply shared edge rate limits for registration/login/pairing; the backend's direct-client-IP limiter is process-local and does not trust forwarded headers.

## Backups, upgrades, and rollback

V3 requires migration `37d6a04b213a`. Research uses outbound public HTTP(S) and Bing RSS;
allow public DNS/HTTPS egress while keeping infrastructure metadata/private networks blocked
at the host firewall too. Research is bounded to 75 seconds in background action workers;
the browser polls progress and can cancel. Run one backend process: the two-worker/eight-task
research limits and task cancellation registry are process-local. Restarted unfinished actions
expire without replay. Captured pages increase database/backup size; audit excerpts survive
conversation deletion. Downgrade refuses while device-less research audit rows exist, rather
than silently deleting their history. See [V3 limits](v3.md).

Back up SQLite while stopped or use SQLite's consistent backup API. Protect backups like live conversations. Keep the vault key in separately restricted recoverable storage. A database-only backup cannot decrypt credentials; a key-only backup cannot restore conversations. Test restoration before accepting other people's data.

Migrations are versioned in `backend/migrations/versions`. Revision `4f853356ea01` creates users, hashed sessions, conversations/turns, provider ciphertext, pairing, devices, and actions. `675b403091a8` widens activity timestamps for millisecond ordering and PostgreSQL integer safety. Revision `ede2ec59ed9a` adds owned personal memories and per-account memory settings without changing existing V1 rows. `6c9c73ac0555` adds the owned, default-off wake preference. Alembic round-trip tests and metadata drift checks cover SQLite. Downgrade removes V1 state at `base`; never do this on production without a separately authorized destructive migration plan. Prefer rollback to a compatible application version, leaving the schema intact.

After restoring an older server or Companion ledger backup, stop existing Companions and revoke/re-pair affected devices. Rolling back execution history can invalidate replay guarantees. Do not manually reset queued/running actions to retry them; create a new user-reviewed request after checking the desktop.

## Remaining production decisions

Account recovery/email verification/MFA, per-account storage quotas, retention/deletion policy and backup erasure, distributed abuse limits, observability without secrets, and disaster recovery are not built in V1. No public rollout or meaningful paid infrastructure should be inferred from the local foundation. Companion has no signed installer/auto-updater or background service yet and supports practical Linux X11/XWayland launching only.

## Optional local speech container

The default image supports all text/memory/Companion APIs and reports speech unavailable.
Build local speech dependencies explicitly with:

```bash
docker build --build-arg INSTALL_VOICE=true -t thryv-backend:v3 backend
```

Download models using the local setup in [V2 setup](v2.md), then mount their directory read-only
at `/models` and set `STT_MODEL_PATH=/models/whisper-base.en` and
`WAKE_MODEL_PATH=/models/thryv-wake` and `TTS_MODEL_PATH=/models/en_US-lessac-medium.onnx`. Wake is explicitly Beta and opt-in. UID 10001 needs read/traverse permission for
those non-secret model files. Model files and voices are not baked into the image. Review the
linked upstream component/model terms before redistribution. Use a single backend worker on a
CPU host with sufficient RAM (allow several GB); concurrent speech has a bounded wait and falls
back to text when busy. Runtime speech stays on this backend host, which may differ from the
user's paired computer. HTTPS is required for microphone access outside localhost.
