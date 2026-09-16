# V4 verification — September 15–16, 2026

V4 combines developer intelligence and connected apps on `feat/thryv-v4`, explicitly
approved by the user. V0–V3 remain supported. Engineering used GPT-6 Astra; DeepSeek
was used only as the runtime provider. No further release or proactive work was started.
Historical [V3 evidence](verification-v3.md) is preserved separately.

## Final regression and release checks

The full regression suite ran once after focused checks and available local live demos.

| Check | Result |
|---|---|
| Backend V0–V4 | **227 passed**; two upstream Starlette/AnyIO deprecation warnings |
| Companion | **52 passed** |
| Browser desktop/mobile | **64 cases verified**: full run had 61 passes and one outdated selector; its focused desktop/mobile recheck passed, followed by six passing V4 cases including two new cases |
| Backend/Companion Ruff lint and format | Passed |
| Frontend lint, TypeScript and production build | Passed |
| Backend/Companion dependency audits | No known vulnerabilities; local Companion package is not on PyPI and is excluded from advisory lookup |
| npm audit | 0 vulnerabilities |
| Fresh SQLite upgrade → full downgrade → upgrade; Alembic drift check | Passed, head `a402_integrations` |
| Default backend Docker build | Passed |
| Disposable production container | Passed: non-root UID, private data modes, health, V4 schema, artifact exclusion and migration consistency |
| Diff and local credential scan | No whitespace errors or configured credential matches; root/backend `.env` remain ignored |

The failed browser case was rerun separately; the full suite was not repeated. Its old
unnamed checkbox locator became ambiguous after OAuth permission controls were added.
It now selects key-storage consent by its accessible name. Upstream Node deprecation
warnings remain; no application lint/type errors remain. No public deployment occurred.

Final diff review also caught hidden Git mutation arguments and hidden development
output in action cards. Both displays were corrected. All six focused V4 browser cases
then passed, including new desktop/mobile coverage for exact Git branch review and
captured test output. Frontend lint, types and production build passed again afterward.

## Focused and live evidence

Focused tests cover workspace ownership/revocation, confined reads and edits, sandbox
isolation, real failing/passing commands, Git staging/commit/stale review, owned server
ports/cleanup, OAuth PKCE/state/ownership/encryption, scopes, service adapters, confirmed
writes/replay, timezone aliases, bounded slow streams and hostile source text. The
final coverage includes 27 V4 backend cases, 20 V4 Companion cases and six V4 browser
cases. Provider cases additionally verify that V4 batches select only one proposal,
discard unobserved completion claims and reject mixed legacy desktop batches.

Opt-in live tests used a locally supplied DeepSeek key and a small synthetic project:

- A real failing unittest was observed. A separately confirmed edit repaired
  `calculator.py`; tests were unchanged. The rerun exited zero, and Git diff was read.
- Actual Git status and latest commits were both retrieved through Companion.
- Project opening required approval and an actual matching VS Code window was observed.
- Synthetic speech through Talk triggered local STT/VAD, discovered the configured
  test profile, requested the existing confirmation, ran the real test and received
  a successful local TTS response. This verifies the pipeline, not arbitrary-room
  microphone accuracy. Wake Beta was left unchanged.

Live checks exposed and resolved missing timezone aliases, batched tool proposals,
missing observed operation arguments, and conversational approval requests that stopped
before creating the actual confirmation card. V4 now carries observed arguments and
replans serially; only a selected typed tool can reach the existing execution gate.
Rejected/discarded proposals are never treated as executed.

Run the opt-in fixture from `frontend/` with `node scripts/live-v4.mjs`. Optional
`--repair`, `--git`, `--vscode`, `--voice` selectors avoid repeating completed demos.
It creates a fixture account, revokes its device, removes its saved provider credential,
logs out, stops its Companion and removes temporary project files. Audit rows remain.
No provider responses, real credentials, screenshots or traces are recorded.

## Connected-app live limitations

GitHub client ID/secret are configured, but no user OAuth grant was connected during
this gate. A real authenticated THRYV GitHub workflow lookup therefore remains
**unverified**, not passed. Finish consent through Settings → Connected Apps → GitHub
with callback `http://localhost:8000/api/integrations/github/callback` for local use.

Google OAuth configuration and test grants were unavailable. Real Gmail send/reply/
forward, Calendar changes, Drive document reads and a live Calendar+Gmail sequence
remain **unverified**. Their adapters, ownership, scoped confirmations and cross-service
orchestration passed fixture tests. No real email or calendar mutation was attempted.

Authenticated local Git push also requires an explicitly opted-in SSH agent and an
existing verified GitHub host key. The project acceptance fixture verified local Git
reads/staging/commit; it did not push a fixture repository. This is separate from the
engineer's authorized release push to the existing THRYV remote.

These missing external grants do not block the other V4 work under the user's scope.
See [security review](security.md) and [V4 setup and limits](v4.md).
