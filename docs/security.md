# THRYV V0 security model

## Trust boundaries

The browser is untrusted input. The backend validates messages, history, roles, key syntax, request bytes, and upstream response shape. Only the orchestrator adds the runtime system message. Model responses are untrusted display content: HTML is skipped, remote images are removed, and link protocols are restricted. No model output is executed, evaluated, or turned into a system action.

The DeepSeek endpoint is fixed to `https://api.deepseek.com`. Users cannot supply provider URLs. Redirect following and environment proxy discovery are disabled on provider clients to avoid forwarding credentials to a different destination. API secrets live in a Pydantic `SecretStr` after header extraction and are unwrapped only to construct the upstream authorization header. This masks accidental representations, but does not encrypt process memory.

The backend has no user/session store. Provider HTTP clients and credentials are request scoped. Only immutable configuration and an admission counter are process scoped. Conversation history is supplied per request and cannot access other requests. The test suite exercises concurrent distinct credentials and histories.

## What is stored

THRYV writes no keys or conversations to disk, database, browser storage, cookies, or application logs. The password input and React state hold the active key; replacing or disconnecting clears references and cancels pending browser work. Refresh/tab closure clears state. Secure erasure cannot be guaranteed by garbage-collected runtimes or the user's browser/OS. Password managers may independently offer to save input despite autocomplete being disabled.

The THRYV host and DeepSeek receive the submitted key/conversation. DeepSeek's handling is governed by its own policies. Host operators must disable request/response-body capture, redact Authorization headers, and avoid crash dumps or error reporting that records locals. Do not add session replay, frontend error capture containing application state, or analytics around forms without a separate privacy design.

## Logging and errors

Controlled event records contain random request IDs, fixed error codes, response status, and elapsed milliseconds. They omit URLs (including query strings), IPs, headers, bodies, exception strings, and traces. FastAPI validation errors are replaced because the default format includes submitted values. DeepSeek failure bodies are discarded because they can echo credentials. Unexpected errors return a fixed error response and record only a fixed event code.

Use `--no-access-log` with Uvicorn. Application startup suppresses HTTPX/HTTPCore debug logs. Configure hosting access logs separately: the app cannot enforce upstream proxy logging rules. Never enable HTTP wire dumps in production. API responses use `Cache-Control: no-store`.

## Browser protections

The frontend sends credentials only in Authorization headers with `credentials: omit`, `cache: no-store`, `redirect: error`, and no referrer. There are no external scripts, fonts or analytics. The CSP restricts scripts to the application origin, connection destinations to the configured backend, frames/objects to none, and form targets to self. Next.js hydration currently requires inline scripts; the policy explicitly allows them, so it is not a nonce-based CSP. React escaping, no raw model HTML, and no user HTML injection remain essential. A stricter nonce policy can be evaluated later if deployment requirements justify dynamic rendering.

Only HTTPS backend URLs are accepted for non-loopback production builds. Production backend settings require an explicit HTTPS frontend origin. CORS is a browser boundary, not authentication or an anti-abuse control. No cookie-based authentication exists in V0.

## Resource bounds

- 150 KB decoded request body, including chunked requests; 10-second receive deadline.
- 8,000-character user message, 20 history messages, 32,000 total context characters.
- Complete alternating turns only; no submitted system/tool role.
- 20 concurrent admitted requests per worker by default, with a safe 503 when full.
- 60-second total provider deadline by default, plus connection/read deadlines.
- 512 KB decoded provider response, 32,000-character reply, 4,096 requested output tokens.
- No automatic inference retries, preventing hidden duplicate spend.

Before public deployment, configure edge-level per-client rate limits, header/body/connection limits, HTTPS, and request timeouts. The guard is per process, and health requests also count toward it. It does not prevent distributed attacks or replace a gateway. The frontend stop action stops waiting and discards stale responses; upstream completion and billing may continue until completion or the backend deadline.

## Verification and future capabilities

Tests use fake credentials to assert secrets do not appear in logs, validation output, provider errors, browser storage or URLs. Production containers exclude `.env`, tests, local environments and artifacts. Dependency audits are part of CI.

Any later tool system must keep the LLM separate from execution authority: a structured tool request is validated, classified by permissions, confirmed when required, executed by trusted code, and reported from observed results. V0 has no tool registry, shell, Companion, browser automation, device access, or multi-agent runtime.
