# THRYV

**Your Personal AI**

Created by Omkar Zunje

THRYV is a personal AI workspace for thinking, writing, learning, and planning. Anyone can connect their own DeepSeek API key and start a conversation. The creator attribution is project metadata; THRYV never assumes who the current user is.

## Current — V0

- Responsive Next.js interface with provider setup, chat, Markdown, starter prompts, loading states, retryable errors, and provider settings.
- DeepSeek BYOK: connection verification through the models endpoint, then chat using the current user's key. No developer key or THRYV account is required.
- One FastAPI backend, one orchestrator, and a small typed provider interface with one DeepSeek implementation.
- Temporary conversations: up to 10 recent complete turns within a 32,000-character request context. Up to 50 turns remain visible in the tab; older visible turns are discarded.
- Explicit disconnect, key replacement, and new-conversation flows. Keys and conversations clear on refresh or tab closure.
- Request limits, safe error normalization, correlation IDs, restricted CORS, automated backend and browser tests, locked dependencies, CI, and a portable backend container definition.

Replies are returned as complete messages, with a waiting indicator and a stop-waiting action. Token streaming is not implemented in V0. Stopping the browser request does not guarantee DeepSeek cancels generation or billing. THRYV has no tools or execution capabilities.

## Architecture

```text
Browser / Next.js
  key + recent conversation in tab memory
        │ HTTPS POST + Authorization: Bearer <user key>
        ▼
FastAPI: request limits → validation → thin API routes
        ▼
Single THRYV orchestrator: identity + bounded conversation
        ▼
DeepSeek provider: per-request HTTP client → DeepSeek API
        ▼
Normalized reply or safe error → browser
```

Next.js 16 / React 19 / TypeScript provide the frontend. Python 3.12+, FastAPI, Pydantic, and HTTPX provide the backend. No database, authentication system, shared user state, queue, or separate orchestration service is needed for V0. There is no OpenAI runtime dependency; development was performed using GPT-6 Astra, while DeepSeek serves runtime inference only.

The default runtime model is `deepseek-flash`, using non-thinking chat completions. This follows the [current DeepSeek API documentation](https://api-docs.deepseek.com/). The provider's response and error handling follow the [chat API reference](https://api-docs.deepseek.com/api/create-chat-completion/) and [error code reference](https://api-docs.deepseek.com/quick_start/error_codes/). Model names can change; `DEEPSEEK_MODEL` is host configuration, and connection verification checks its availability.

## Local development

Prerequisites: Node.js 24 LTS, npm, Python 3.12+, and [uv](https://docs.astral.sh/uv/getting-started/installation/). Use a DeepSeek key with API credit for a real conversation. Ordinary tests use fakes and make no paid requests.

From the repository root, prepare the backend:

```bash
cd backend
cp .env.example .env
uv sync --locked
uv run uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload --no-access-log
```

In another terminal, prepare the frontend:

```bash
cd frontend
cp .env.example .env.local
npm ci
npm run dev
```

Open **http://localhost:3000**. Paste your DeepSeek key into the password field, select **Connect & get started**, and send a message. The connection check verifies authentication and model availability without generating a paid completion; credit availability is checked by DeepSeek when you send a message. Provider settings let you connect another key or disconnect. A new conversation clears the current conversation after confirmation and retains the connection.

The default backend CORS origin is exactly `http://localhost:3000`. If you open the frontend at a different hostname or port, update `FRONTEND_ORIGIN` to match. Do not add a trailing slash.

## Configuration

| Location | Variable | Default / purpose |
| --- | --- | --- |
| `frontend/.env.local` | `NEXT_PUBLIC_API_URL` | `http://localhost:8000`; backend origin, compiled into the frontend at build time |
| `backend/.env` | `APP_ENV` | `development`; `production` requires an HTTPS frontend origin and disables API docs |
| `backend/.env` | `FRONTEND_ORIGIN` | One explicit allowed origin, default `http://localhost:3000` |
| `backend/.env` | `LOG_LEVEL` | `INFO`; controlled application metadata only |
| `backend/.env` | `DEEPSEEK_MODEL` | `deepseek-flash` |
| `backend/.env` | `PROVIDER_TIMEOUT_SECONDS` | 60 seconds, range 1–120; frontend waits at most 70 seconds |
| `backend/.env` | `MAX_CONCURRENT_REQUESTS` | 20 in-flight requests per process, range 1–200 |
| Container environment | `PORT` | 8000; used by the container start command and health check |

For local Uvicorn commands, set the port using `--port`; `PORT` is a container convention. Keep `PROVIDER_TIMEOUT_SECONDS` at or below 60 unless you also adjust the frontend deadline and host timeouts.

**Never create `NEXT_PUBLIC_DEEPSEEK_API_KEY`.** All `NEXT_PUBLIC_*` values are public. The backend does not read a developer API key for runtime use.

## Key safety and privacy

- The key exists in the browser password field/React memory and temporarily in the current backend/provider request. It is not placed in URLs, cookies, local storage, session storage, a database, or a server session.
- Every authenticated request uses that user's `Authorization` header. A separate HTTP client for each request prevents credentials or upstream cookies from crossing between users.
- Production frontend and backend must both use HTTPS. The THRYV host necessarily handles the key and conversation in memory while forwarding them to DeepSeek. Choose a host you trust. Local HTTP is for loopback development only.
- THRYV logs controlled error codes, status, duration, and random request IDs. It excludes headers, request bodies, provider error bodies, raw exception messages, and stack traces. HTTP debug/access logging is disabled by the application; documented launch commands also disable Uvicorn access logs.
- No application analytics, remote fonts, or conversation telemetry is installed. Remote images in model Markdown are disabled to prevent tracking requests; raw HTML is not rendered, and links use restricted protocols and no referrer.
- THRYV does not save keys or conversations. This does **not** determine DeepSeek's own data retention policy or a hosting provider's request capture behavior. See [security details](docs/security.md).
- `.env` files are ignored. Examples contain configuration only. Browser tests use obvious fake keys, with trace recording disabled.

## API

| Endpoint | Behavior |
| --- | --- |
| `GET /health` | Local process health: `{"status":"ok","service":"THRYV"}`; does not contact DeepSeek |
| `POST /api/provider/connect` | Requires bearer key; verifies it and the configured model through DeepSeek `/models` |
| `POST /api/chat` | Requires bearer key; accepts `message` and optional `history`, returns `message` and `truncated` |

Example chat body, without a credential:

```json
{
  "message": "What color did I mention?",
  "history": [
    { "role": "user", "content": "My favorite color is green." },
    { "role": "assistant", "content": "Green — got it for this conversation." }
  ]
}
```

Messages have an 8,000-character limit; history must alternate complete user/assistant pairs, with no client-supplied system or tool messages. The backend rejects context over 32,000 characters or 20 history messages. The browser drops oldest whole turns to fit. HTTP bodies are capped at 150,000 bytes, with a 10-second receive deadline. DeepSeek responses are capped at 512,000 bytes and 32,000 visible characters; generation requests allow 4,096 output tokens. Length-limited replies are marked in the UI.

Errors use `{"error":{"code":"invalid_key","message":"…"}}`. Failure categories include invalid/revoked keys, insufficient credit, throttling, timeout, network/provider failure, invalid model output, invalid input, and overloaded THRYV instances. Responses are `no-store` and carry a generated `X-Request-ID`.

## Testing and production builds

```bash
cd backend
uv run pytest -q
uv run ruff check app tests
uv run ruff format --check app tests
uv run pip-audit
```

```bash
cd frontend
npm run lint
npm run typecheck
npm run build
npm audit --audit-level=moderate
npx playwright install chromium
npm test
```

Playwright is a **development test dependency only**, not a THRYV runtime capability. It starts a test-only FastAPI server on port 8001 with a mocked DeepSeek HTTP transport and a Next.js server on port 3001. Desktop and mobile browser tests exercise the actual frontend → backend → orchestrator → provider integration without real credentials. Test traces are off; screenshots contain fake sessions only. Tests never read a real key from `.env`.

Backend tests cover health, connection verification, context, schema failures, secrets in malformed inputs/errors, provider errors, redirects, timeouts, response validation, user isolation, body limits, concurrency admission, and CORS. CI runs the checks on pushes and pull requests.

To run the built frontend locally:

```bash
cd frontend
npm run build
npm start
```

Run the backend separately as above. See [deployment preparation](docs/deployment.md) for frontend host and backend container configuration. **V0 has not been authorized for public deployment.**

An optional manual browser smoke test is available after starting the real backend and frontend on ports 8000 and 3000. Add `DEEPSEEK_API_KEY` to ignored `backend/.env` locally, then run `node scripts/live-smoke.mjs` from `frontend/`. This makes **two paid chat requests** using that key, checks identity and follow-up context, and separately tries a fake invalid key. It prints pass/fail labels only, records no screenshots or traces, and disconnects afterward. The backend ignores this environment key for runtime requests. Remove the optional local entry when finished if you do not want to retain your development test credential on disk.

## Current limitations

- One DeepSeek provider, complete-message replies, and temporary text conversations only.
- No accounts, saved keys, saved conversations, long-term memory, files, tools, browser/computer control, voice, or integrations.
- Context is bounded; earlier details can fall out of context even while some remain visible.
- Keys are held in normal process memory, not a hardware vault; JavaScript cannot guarantee secure memory erasure. Browser extensions and host-level logging are outside the app's control.
- The per-process concurrency guard and body/time limits are an abuse foundation, not a distributed rate limiter. Public hosting needs HTTPS and edge request/connection/rate limits.
- Provider connection verification does not guarantee sufficient API balance, future service availability, or answer accuracy.

## Planned

The next milestone should review V0 and authorize a controlled public deployment with HTTPS, host log redaction, edge abuse protection, and live acceptance checks. This repository prepares that deployment but does not publish it.

Later milestones may add opt-in authenticated persistence, additional runtime providers, streaming, and a separately installed THRYV Companion. Any future action capability must follow input validation → permission evaluation → execution → observed result. Raw model output must never be trusted execution authority. Voice, browser control, device access, memory, integrations, and automations remain future work.

## Project map

- `frontend/components/workspace.tsx`: setup, session lifecycle, conversation and settings UI.
- `frontend/components/provider-setup.tsx`, `brand.tsx`: connection form, welcome screen and shared branding.
- `frontend/lib/api.ts`: safe requests and bounded conversation history.
- `frontend/app/`: Next.js entry points, THRYV styling and icon.
- `backend/app/api.py`: thin routes and per-request credentials/provider dependencies.
- `backend/app/orchestrator.py`: single orchestrator and THRYV identity.
- `backend/app/providers/`: provider protocol and DeepSeek HTTP integration.
- `backend/app/middleware.py`: request limits and safe request logging.
- `backend/app/config.py`, `schemas.py`, `errors.py`, `main.py`: configuration, validation, errors and lifecycle.
- `backend/tests/`, `frontend/tests/`: isolated automated coverage.
- `docs/`: security, deployment and verification documentation.

Development boundary: use GPT-6 Astra for engineering. DeepSeek is a runtime provider, not a source-code author. Stop at V0; subsequent milestones need explicit instruction.
