# THRYV engineering boundaries

THRYV — **Your Personal AI**. Created by Omkar Zunje. Creator attribution must never
become a runtime assumption about the user.

## Development model

Use **GPT-6 Astra only** for engineering, review, testing, debugging and documentation.
Verify the active model using session metadata when available. If Astra is unavailable,
stop; do not substitute another coding model. DeepSeek is the runtime provider only.

## Scope

The authorized milestone is **V0 only**: Next.js + TypeScript, FastAPI + Python,
DeepSeek BYOK chat, one orchestrator, bounded session context, and deployment preparation.
Do not begin authentication, persistence, other providers, voice, browser/computer
control, Companion, tools, memory, email, automations or payments without a new instruction.
Browser automation under `frontend/tests` is development testing, not a runtime feature.

## Security invariants

- Keys and conversations stay in tab memory and request-scoped backend memory.
- No global current-user state, shared credentials, developer runtime key or database.
- Never log or commit keys, headers, conversations, `.env`, tokens or raw provider errors.
- Never expose credentials through public environment variables, URLs or telemetry.
- Production origins use HTTPS and explicit CORS. Keep upstream URLs fixed.
- Keep provider logic separate from thin routes and the one orchestrator.
- Never interpret model output as execution authority. V0 executes no model-requested tools.
- Mock DeepSeek in ordinary tests. Live smoke testing is explicit and opt-in, with a
  locally provided key; never capture real credentials in browser traces or screenshots.

## Workflow

Inspect Git state and existing work first. Independently implement, debug, install project
dependencies, test, run local servers, update documentation and prepare builds as needed.
Normal branches, commits and pushes to the existing GitHub remote are authorized.
Before committing/pushing, inspect the diff, verify secrets are ignored and absent, and
run relevant checks. Do not discard unrelated user work.

Ask before destructive history rewrites, force pushes, deleting substantial existing work,
destructive system/production operations, or meaningful paid infrastructure. Public
deployment requires Omkar's explicit **"Deploy V0 now"** instruction.

## Checks

Backend, from `backend/`:

```bash
uv sync --locked
uv run ruff check app tests
uv run ruff format --check app tests
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
After V0 is tested, documented, committed and pushed, stop and wait for the next milestone.
