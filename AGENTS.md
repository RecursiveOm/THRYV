# THRYV engineering boundaries

THRYV — **Your Personal AI**. Created by Omkar Zunje. Creator attribution must never
become a runtime assumption about the user.

## Development model

Use **GPT-6 Astra only** for engineering, review, testing, debugging and documentation.
Verify the active model using session metadata when available. If Astra is unavailable,
stop; do not substitute another coding model. DeepSeek is the runtime provider only.

## Scope

Finish **V2 first**: local push-to-talk speech and explicit user-owned
personal memory, with a consistent warm, truthful personality. Include silence-based VAD and
explicit opt-in wake listening for the one fixed THRYV keyword; no custom wake-word field.
Preserve V0/V1.
Finish tests, live acceptance, security review, migrations, documentation, commit and push.
Wake listening is explicitly Beta, off by default; documented imperfect accuracy does not
block V2 when stable voice and permission safeguards pass. Do not further tune wake models.
After V2 passes, is committed and pushed, implement **V3 browser + live research only** using
the existing orchestrator and permission boundaries. Use isolated public browsing, bounded
research, real source grounding and prompt-injection defenses. Do not start V4 or add email/calendar/Drive, scheduling,
proactive tasks, payments, broad provider support, code-editing agents, or unrestricted
terminal. No sub-agents are requested.

## Security invariants

- THRYV account identity is independent of DeepSeek keys; authorize every resource server-side.
- Saved provider keys require explicit consent and authenticated encryption under a separate
  server-only key. Only token hashes persist on the backend. No shared current-user state.
- Never log or commit credentials, headers, messages, `.env`, tokens, or raw provider errors.
- Production requires HTTPS, exact CORS, secure HttpOnly cookies, and CSRF checks on writes.
- The model requests typed tools; trusted code owns allowlists, permissions, and authorization.
- No shell, arbitrary command/executable/arguments, file access, or unrestricted device access.
- Pairing/confirmations expire and are single-use. Device revocation and durable replay guards
  must remain enforced. Never claim action success before the observed execution result.
- Ordinary tests mock DeepSeek and desktop side effects. Real acceptance checks are opt-in;
  use only a locally provided key and never record real credentials in traces/screenshots.

## Workflow

Inspect Git state and existing work first. Independently implement, debug, install project
dependencies, test, run local servers, update documentation and prepare builds as needed.
Normal branches, commits and pushes to the existing GitHub remote are authorized.
Before committing/pushing, inspect the diff, verify secrets are ignored and absent, and
run relevant checks. Do not discard unrelated user work.

Ask before destructive history rewrites, force pushes, deleting substantial existing work,
destructive system/production operations, or meaningful paid infrastructure. Public
deployment requires Omkar's explicit deployment instruction.

## Checks

Backend, from `backend/`:

```bash
uv sync --locked
uv run ruff check app tests migrations scripts
uv run ruff format --check app tests migrations scripts
uv run pytest -q
uv run pip-audit
```

Frontend, from `frontend/`:

```bash
npm ci
npm run lint
npm run typecheck
npm run build
npm audit --audit-level=moderate
npx playwright install chromium
npm test
```

Keep README and `docs/` accurate. Report any unverified acceptance checks honestly.
Companion checks: `uv run --project companion ruff check companion`, `uv run --project companion pytest companion/tests -q`, and its dependency audit.
Close V2 and push before starting V3. After V3 passes, document, review, commit and push,
report verified results and remaining limitations, then stop. Do not begin V4.
