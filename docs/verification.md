# THRYV V0 verification report

Date: 2026-09-10. Engineering model: **GPT-6 Astra**, verified from the active session's `turn_context` metadata before implementation.

## Status

V0 implementation, automated tests, production builds, local launch checks and security review are complete. **A valid-key live identity/follow-up smoke test is still pending.** The user elected to supply a key in ignored `backend/.env`; its optional `DEEPSEEK_API_KEY` field was empty at the last check. No paid completion was attempted. Do not treat mocked responses as proof of successful live inference.

## What was built and user flow

Users open THRYV, see **Your Personal AI** with separate **Created by Omkar Zunje** attribution, supply a DeepSeek key, and connect. They can chat with bounded recent context, read formatted Markdown, stop waiting, retry failures, start a new conversation, replace their key, or disconnect. Refreshing clears the tab's key and conversation. No account is required.

## Architecture and important files

| Files | Purpose |
| --- | --- |
| `frontend/components/provider-setup.tsx`, `brand.tsx` | Welcome, branding and verified provider connection |
| `frontend/components/workspace.tsx` | Conversation, cancellation, settings and session lifecycle |
| `frontend/lib/api.ts` | Safe browser requests, error copy and bounded history |
| `frontend/app/`, `next.config.ts` | Next.js pages, responsive styling, metadata and security headers |
| `backend/app/api.py`, `schemas.py` | Thin API routes, request credentials and validated schemas |
| `backend/app/orchestrator.py` | One provider-independent orchestrator and THRYV runtime identity |
| `backend/app/providers/` | Typed provider protocol and the single DeepSeek integration |
| `backend/app/main.py`, `middleware.py`, `config.py`, `errors.py` | Lifecycle, limits, logging, configuration and error normalization |
| `backend/tests/`, `frontend/tests/` | Backend and full browser/backend mocked integration coverage |
| `backend/Dockerfile`, `.dockerignore` | Portable non-root production image with health check |
| `.github/workflows/ci.yml` | Backend/frontend validation on push and pull request |
| `README.md`, `docs/`, `AGENTS.md` | Setup, boundaries, privacy, deployment and verification |

The runtime flow is browser → FastAPI → one orchestrator → DeepSeek provider → normalized reply. No developer key, shared credential state, database, Companion, tool execution, voice, memory or additional runtime provider was added.

## Tests and checks

| Command / check | Result |
| --- | --- |
| `uv run pytest -q` | **62 passed** |
| `uv run ruff check app tests` | Passed |
| `uv run ruff format --check app tests` | Passed, 16 files |
| `uv run python -m compileall -q app` | Passed |
| `uv run pip-audit` | No known vulnerabilities |
| `npm ci --ignore-scripts` | Reinstalled successfully from lockfile |
| `npm run lint` | Passed |
| `npm run typecheck` | Passed |
| `npm test` | **24 passed**, 12 scenarios each on desktop and mobile Chromium |
| `npm run build` | Production Next.js build passed; pages prerendered |
| `npm audit --audit-level=moderate` | Zero reported vulnerabilities |
| `docker build -t thryv-backend:v0 ./backend` | Passed |
| Production backend container | Healthy; UID 10001; `.env` and tests absent; `/docs` returns 404 |
| `git diff --check` / staged diff check | Passed |

Backend coverage includes valid chat/follow-up schemas, malformed inputs, empty/oversized content, missing or invalid credentials, model verification, provider protocol behavior, invalid responses, redirects, HTTP/network errors, total timeouts, concurrent request isolation, CORS, body limits, admission limits, and sanitized logs/errors.

Browser coverage includes setup, chat, contextual follow-up, settings/disconnect, invalid-key retry, storage and URL safety, timeout recovery, unreachable backend, safe Markdown, new conversations, responsive layout, history trimming, cancellation/stale replies, separate tabs, and key replacement. Tests use a test-only backend with the real provider adapter over `httpx.MockTransport`. There is no production mock switch.

A cancellation regression was found and fixed: a Stop button reused as a Submit button could accidentally submit again during the same click. Separate button identities and prevention of the click's default action now preserve the draft and discard stale replies.

## Manual/local integration verification

- Real FastAPI backend launched on loopback port 8000; health passed.
- Built Next.js frontend launched on loopback port 3000; HTTP 200, expected security headers, and no observed JavaScript runtime errors in the production browser check.
- Real DeepSeek invalid-key verification returned HTTP 401 with `invalid_key`. The production browser displayed the controlled error message without a crash.
- Desktop and mobile setup/chat screenshots were visually inspected. Additional production setup overflow checks passed at widths **320, 390, 768 and 1366** pixels. This is browser emulation, not physical-device certification.
- Successful identity and contextual follow-up passed through the entire mocked browser/backend/provider flow. **The equivalent two paid DeepSeek completions have not been verified.**

Run `node scripts/live-smoke.mjs` from `frontend/` after supplying the optional local key and starting the real services. It makes two chat requests, checks identity/follow-up, checks invalid-key behavior and browser key safety, and emits only controlled pass/fail labels. No live-key screenshots or traces are recorded.

## API-key security review

The user's key exists in browser memory and the current backend/provider request. Authorization headers carry it to the backend and DeepSeek; production requires HTTPS. No key is put in browser bundles, URLs, browser storage, cookies, server sessions or databases. There is no global current-user key. Per-request clients also isolate upstream cookies.

Logs exclude secrets, headers, full conversations, provider error bodies and raw exceptions. Validation errors do not echo submitted inputs. Runtime source was inspected for credential patterns, owner-specific assumptions, wildcard CORS, unsafe rendering and execution capabilities. Ignored local environment files and generated artifacts are excluded from the Git change. The deployment image excludes local secrets and test fixtures.

These checks cover THRYV code, not the hosting provider's future logging configuration, browser extensions, secure erasure of garbage-collected memory, or DeepSeek's own retention. The host must enforce HTTPS, redact upstream request logging and configure edge abuse protection before a public release.

## Git and deployment

Working branch: `feat/thryv-v0`. Authorized remote: `https://github.com/RecursiveOm/Thryv.git` (GitHub resolves the repository name as `RecursiveOm/THRYV`). The final commit and push result are reported in the handoff; use `git log -1 --oneline` to identify the checked-out revision.

No public production URL, hosting account, paid infrastructure or public deployment was created. The backend test container was stopped after verification.

## Known limitations and next milestone

V0 provides temporary text chat using one DeepSeek provider. It does not stream tokens, persist conversations or keys, authenticate users, or execute actions. Context and visible history are bounded. Stop-waiting does not guarantee cancellation of upstream billing. The per-process admission guard needs edge rate limits for public hosting.

The development dependency tree currently emits upstream deprecation warnings: Next.js's bundled lint plugins require ESLint 9 rather than ESLint 10, and Starlette's test client emits HTTPX/AnyIO migration warnings. The configured checks pass and audits report no known vulnerabilities; these warnings do not come from runtime application behavior.

Finish the valid-key smoke test and review V0. The recommended next milestone is an explicitly authorized controlled public deployment with HTTPS, log redaction, edge abuse protection and live acceptance checks. No next-milestone implementation has begun.
