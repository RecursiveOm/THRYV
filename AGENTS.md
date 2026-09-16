# THRYV engineering boundaries

THRYV — **Your Personal AI**. Created by Omkar Zunje. Creator attribution must never
become a runtime assumption about the user.

## Development model

Use **GPT-6 Astra only** for engineering, review, testing, debugging and documentation.
Verify the active model using session metadata when available. If Astra is unavailable,
stop; do not substitute another coding model. DeepSeek is the runtime provider only.

## Scope

The user has explicitly authorized **V4: developer intelligence and connected apps**
on `feat/thryv-v4`, combining the planned developer and integration work. Preserve V0–V3.
Use locally authorized workspaces, fixed sandboxed commands, typed Git operations and
owned GitHub/Gmail/Calendar/Drive OAuth connections through existing confirmations.
No unrestricted terminal, proactive tasks, reminders, payments or additional releases.
Wake listening remains Beta, off by default, with one fixed THRYV keyword; do not tune it.
Finish focused tests and live acceptance first, then one full regression gate, security
review, migrations, documentation, commit and push. Report unavailable live credentials
honestly. Stop after V4. No sub-agents are requested.

## Security invariants

- THRYV account identity is independent of DeepSeek keys; authorize every resource server-side.
- Saved provider keys require explicit consent and authenticated encryption under a separate
  server-only key. Session/device token hashes persist; OAuth tokens require authenticated
  encryption bound to owner and service. No shared current-user state.
- Never log or commit credentials, headers, messages, `.env`, tokens, or raw provider errors.
- Production requires HTTPS, exact CORS, secure HttpOnly cookies, and CSRF checks on writes.
- The model requests typed tools; trusted code owns allowlists, permissions, and authorization.
- No model-supplied shell, arbitrary executable/arguments, unrestricted file or device access.
  Project access requires explicit local grants; execute only fixed sandboxed profiles.
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
After V4 passes, document, review, commit and push, report verified results and remaining
limitations, then stop. Do not begin another release.
