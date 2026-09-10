# THRYV V1 verification

Date: 2026-09-11. Engineering model: **GPT-6 Astra**, verified again from the current session's `turn_context` before continuing. V0's historical report is preserved in [verification-v0.md](verification-v0.md); its temporary-session descriptions do not describe V1.

## Acceptance status

The V1 foundation is implemented. A real authenticated Companion check successfully opened Chrome, observed a new window, recorded the result, and verified revocation. **The full live DeepSeek → structured tool → user confirmation → Chrome demo remains unverified because `DEEPSEEK_API_KEY` is absent from the user's ignored local configuration.** The opt-in live script exits with code 2 and a controlled pending message. No fake model response is being counted as live inference. V1's completion gate is therefore not yet satisfied, and V2 is not ready to begin.

## Added architecture

- FastAPI Users registration/password handling, Argon2, random database sessions, hashed token storage, seven-day expiry, HttpOnly/SameSite=Lax cookies, production Secure flag, exact-Origin/custom-header CSRF checks.
- SQLAlchemy async durable state with SQLite as the tested single-host default and two versioned Alembic migrations. Owned chats retain chronological turns; recent activity uses millisecond timestamps; server generation context remains bounded.
- Explicit-consent Fernet encryption for saved DeepSeek keys, bound to owner UUID and held separately from account/device credentials. Removing/replacing the key preserves chats.
- Outbound scoped Companion, single-use five-minute pairing, unique owned device credentials, heartbeat/status, revocation, local 0600 credentials and a durable replay ledger.
- Typed registry and fixed SAFE/CONFIRM/BLOCKED policy. Chrome/VS Code launches require an expiring, same-session, single-use approval; basic OS/architecture is SAFE. No shell or arbitrary executable/arguments exist.
- High-level durable action records, conditional claim/result transitions, sanitized error codes, and truthful chat updates from observed results.
- Existing branded UI extended with authentication, persisted/recent chats, selected chat restoration, provider consent, device selection/pairing, confirmations, Recent Actions, deletion, and logout.

## Automated checks

Final regression results: **92 backend tests, 22 Companion tests, and 28 browser tests passed**. Browser tests run the same scenarios on desktop and mobile Chromium. Ordinary tests mock all paid provider requests and real desktop side effects.

| Check | Result |
| --- | --- |
| Backend pytest | 92 passed; two upstream deprecation warnings |
| Companion pytest | 22 passed |
| Playwright browser/backend integration | 28 passed, desktop + mobile Chromium |
| Backend/Companion Ruff lint and format | Passed |
| Frontend ESLint and TypeScript | Passed |
| Next.js production build | Passed |
| Backend pip-audit | No known vulnerabilities |
| Companion pip-audit | No known dependency vulnerabilities; local unpublished Companion package is not a PyPI audit target |
| npm audit | Zero reported vulnerabilities |
| Alembic metadata drift + round-trip migration test | Passed |
| Docker V1 image build | Passed |
| Non-root production container smoke | Passed: migration, private volume/file permissions, health, disabled docs, secret/test exclusion, schema consistency |
| Real Companion/Chrome test repeated on September 11 | Passed: observed window, audit result, revocation and no redispatch |
| Full live DeepSeek acceptance script | Pending; exit 2 because no local key is configured |

Playwright uses a separate `.next-test` build directory so tests can run alongside the user's existing development server without stopping it. A container verification failure exposed a generated migration file with private source-file permissions; the image now explicitly grants read access to application/migration source while retaining private database/secret permissions. `backend/scripts/container_smoke.py` reproduces the disposable-volume check.

Backend coverage includes the original V0 scenarios plus session persistence/logout/expiry, password privileges, CSRF/rate limits, owner isolation, consent/encryption/owner binding, migration drift and upgrade/downgrade, chronological/deduplicated chats, token-purpose separation, device online/offline/revocation, unsupported tools/apps, confirmation ownership/session/expiry/denial, result compatibility, deadline handling, structured model response parsing, sanitized logs, and concurrent pairing/action/approval/dispatch replay attempts.

Companion coverage includes TLS-origin policy, private/exclusive credential files, injection rejection before process creation, fixed argv with `shell=False`, observed-window success, missing/unconfirmed applications, bounded system information, scoped authentication, persistent replay prevention after reopening its ledger, final authorization revocation, and result retries without re-execution.

Browser coverage retains all twelve V0 scenarios, updating the explicitly superseded reload/disconnect/key-replacement expectations. Two additional scenarios cover pairing/approval/audit/revocation and logout/login restoration. Markdown, provider errors, cancellation, request/console/storage key safety, responsive overflow, follow-up context, and separate-tab restoration remain tested.

The CI workflow covers backend, frontend, and Companion checks. Two upstream Starlette/AnyIO test-client deprecation warnings remain; no warning is treated as a passed live acceptance test.

## Real desktop verification

The explicit manual script is `companion/scripts/manual_smoke.py`, run with:

```bash
uv run --project companion python companion/scripts/manual_smoke.py
```

It uses a temporary local account and the real running backend. It pairs a device, verifies that a CONFIRM request is not dispatched before approval, allows a fixed Chrome action, runs the actual Companion protocol/executor, verifies the saved result, verifies that the action is not dispatched twice, revokes the device, and checks that Companion authentication stops. It does not call or simulate a model. It leaves only sanitized test account/action metadata and a revoked device in the local database; its temporary local credential state is removed and its session is logged out.

Observed result, repeated successfully in the current session:

```text
PASS pairing, ownership and pre-approval dispatch block
PASS real Chrome window observed, structured result saved in audit
PASS revocation stops Companion; no repeated execution
```

The first attempt reported `launch_unconfirmed` correctly. The desktop's existing Chrome instance ran on native Wayland and forwarded new launches without creating an observable X11 window. A fixed dedicated local Chrome profile now permits reliable X11/XWayland window verification. The successful test used real installed Chrome and did not mock process creation or window observation.

## Full live acceptance procedure

Start real backend/frontend on the default local origins. Add a valid key locally as `DEEPSEEK_API_KEY` in ignored `backend/.env`; never paste it into chat. From `frontend/`, run:

```bash
node scripts/live-smoke.mjs
```

This explicitly opt-in test uses real DeepSeek completions and opens a real Chrome window. It creates/signs into an isolated test account, connects the key with consent, chats, reloads, pairs and starts the actual Companion, asks “Open Chrome on my laptop.”, approves the model-requested action, waits for observed-window success and audit UI, revokes the device, repeats the command, and verifies that it cannot execute. It checks browser key safety without screenshots/traces. Cleanup removes the saved provider key, revokes the device, signs out, stops the test Companion, and removes its private temporary state. It leaves the opened Chrome window and sanitized account/chat/action metadata. It outputs only controlled stage labels, never raw Playwright errors or credentials.

## Security and deployment

See [security.md](security.md) for the implemented threat controls and limits. Review found and fixed a vulnerable dependency pin: cryptography 49 was upgraded to patched version 50. The source contains no unrestricted execution path, developer-owned runtime credential, wildcard credentialed CORS, or client-only ownership check. Dependency audit results and secret scanning are rechecked before committing.

No public service, paid infrastructure, external notification, merge to main, or V2 feature is authorized or created. SQLite single-host scale, trusted Companion reporting, the narrow revocation/in-flight race, account recovery/MFA omissions, and non-encrypted conversation storage remain explicit limitations.

## Git handoff

Branch: `feat/thryv-v1`, based on V0 commit `6f33a7a`. The user authorized normal commits and pushes to `https://github.com/RecursiveOm/Thryv.git`. Final commit/push status is reported in the handoff. Pending live acceptance must remain visible in that report.
