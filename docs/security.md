# THRYV V2 security design and review

The inherited V1 foundation separates account identity, provider credentials, and device credentials. The server is trusted to hold account data and decrypt saved DeepSeek keys. Companion is trusted to execute the two implemented handlers and report honestly. A compromised backend can authorize those handlers; a compromised desktop user can already run arbitrary programs outside Companion. Neither is a sandbox against its own administrator.

## Identity and ownership

FastAPI Users 15 supplies registration, password verification, and expiring database-session behavior. The default password helper uses Argon2. Registration requires a 12–128 character password, and safe registration cannot grant superuser/verified flags. Password recovery, email verification, MFA, account deletion, and session management across all devices are not V1 features. A public service needs an account recovery/abuse policy before launch.

Session tokens are cryptographically random 256-bit values. SHA-256 token digests persist, using the library's database strategy and absolute expiry. Logout removes the current session row. Session cookies are host-only, HttpOnly, SameSite=Lax, path `/`, and Secure in production. Do not host untrusted applications on the same cookie host. Other browser sessions remain valid when one session signs out.

All conversation/device/action lookups bind IDs to the authenticated owner. Cross-user access returns 404; API/provider/device tokens cannot substitute for an account session. Device operations bind the credential to a non-revoked device and its owner. Browser mutations require exact Origin and a non-simple request header, including login, registration, and logout. This prevents form-based and cross-origin CSRF; it does not mitigate same-origin XSS. Existing CSP, protocol-restricted links, disabled Markdown HTML/images, no analytics, and safe errors reduce that surface. Next's static rendering currently requires inline-script permission; a strict nonce-based CSP is not claimed.

## Provider-key vault

Explicit browser checkbox consent is required before saving a key. Fernet provides authenticated encryption using a separately injected `CREDENTIAL_ENCRYPTION_KEY`; encrypted JSON binds the key to the owner's UUID. Ciphertext swapped across owners or modified is rejected. Keys are verified before persistence. Removing a key deletes the current ciphertext row. It does not instantly erase copies from database backups, disk free space, or storage journals.

Only a user's current request decrypts their credential. Keys are never placed in device messages, session cookies, frontend storage, URLs, logs, or API responses. No fallback server-owned runtime key exists. Trusting the host remains necessary: encryption at rest does not prevent the running server or a host administrator from using its decryption key. Back up that key separately and restrict it with host secret controls. There is no automatic key-rotation UI; rotate by replacing the key and reconnecting providers, or implement a reviewed MultiFernet migration before rotating without reconnects.

Conversation text itself is stored normally in the database. Protect the data directory and backups with filesystem permissions and disk encryption appropriate to the host. SQLite database creation during migration uses umask 077; the local initializer also restricts an existing default database to 0600. The Docker data directory is 0700. Do not enable SQL echo, request body capture, tracing, or proxy header logging.

## Pairing and device credentials

A signed-in account requests a 256-bit pairing capability. Only its digest, owner, five-minute expiry, and used state persist. One atomic conditional update redeems it once and creates a device for the issuer's account. The redeeming client cannot submit a user ID. Anyone possessing an unused token can pair to that account, so the UI hides it and the terminal prompt does not echo it. There is no short guessable PIN or discoverable pairing endpoint.

Each device receives a separate random scoped credential; the backend stores its digest. Local Companion stores it in an exclusive-created 0600 file under a user-owned 0700 directory. File/symlink checks reduce accidental disclosure. It is a bearer credential: malware running as the desktop user can steal it. Revoke lost or suspect devices. The token does not authenticate account/chat/provider APIs and cannot obtain a DeepSeek key.

Companion only initiates outbound HTTP requests. HTTPS verification is enabled; redirects and proxy-environment inheritance are disabled. HTTP is accepted only for literal loopback hostnames. No incoming listening port, remote shell, or public callback is opened. Polling uses two-second intervals, ten-second network timeouts, and bounded exponential backoff up to thirty seconds. A 401 stops the process instead of retrying indefinitely.

## Tool authority and replay prevention

The model supplies a tool name and structured arguments, never executable authority. The backend registry defines typed, extra-forbidden input and fixed permissions:

- `open_application`: CONFIRM; only `chrome` or `vscode`.
- `get_system_info`: SAFE; no arguments, only bounded OS/architecture enums returned.
- Other capabilities: BLOCKED. Extra permission fields, paths, URLs, and shell strings are rejected.

The selected device is supplied by the authenticated UI request and independently ownership-checked, never chosen through model arguments. Application requests require a currently online non-revoked device. Confirmation is bound to the initiating session digest, user, action ID, device, and immutable validated arguments. It expires after 120 seconds. Atomic state transitions consume allow/deny once. A different login session for the same account cannot approve it; the UI explains this error. A SAFE tool still requires authenticated ownership and a live paired device.

Action records are durable with a unique user/request ID. Device row locks serialize action creation and result acceptance against revocation. Conditional claims dispatch queued actions once into running status; no automatic redispatch occurs. Companion records action IDs in a durable SQLite ledger **before** executing and rechecks server authorization immediately before the side effect. Result delivery retries only sanitized results, never the launch. Duplicate claims, approvals, and results are rejected. A crash after recording but before execution produces uncertainty rather than replay. Restoring old database/Companion backups can weaken replay history; stop Companions and revoke/re-pair devices after rollback.

Revocation cancels pending/queued/running records and prevents subsequent authentication. It cannot undo an already-started process or atomically prevent a launch in the narrow interval after the final authorization response. THRYV does not claim otherwise. A lost response or execution deadline returns an unknown/unconfirmed outcome; manually check the desktop before requesting another action.

## Local execution

No `run_command`, shell grammar, user-supplied executable, arbitrary argument list, URL, or file path is accepted. The executor uses `subprocess.Popen` with `shell=False`, trusted absolute installed paths, fixed flags, closed input/output streams, and no provider credentials. Executable and parent ownership/modes must be root-owned and not group/world writable. V1 supports Linux applications only and runs without elevation.

Chrome opens a fixed blank page using a dedicated 0700 profile and X11 flags. This avoids native Wayland process forwarding that prevents verifying a new window. It never automates browser pages or reads browser history. Xlib inspects only window IDs/classes and mapped state, not titles, screenshots, content, or keystrokes. A new matching mapped window must be observed before `application_opened`. A process launch alone is not success. This observational check can be spoofed by another process with access to the same display; it is not a cryptographic desktop attestation. VS Code forwarding into an unverifiable native Wayland window may produce `launch_unconfirmed`.

## Auditing, limits, and operations

Per-action records retain owner, device, tool, validated arguments, permission, current status, creation/expiry timestamps, and sanitized result. Deleting a chat keeps its action records, with the conversation reference cleared. There is no user-facing action deletion API. Records are not an immutable transition-by-transition audit service. Invalid requests log controlled error codes; rejected arbitrary model text is not copied into the action database.

Application logs contain random request IDs, status, duration, and fixed error codes. Header/body/provider error/exception text is suppressed, and HTTP/SQL debug loggers are disabled. Boundaries limit bodies to 150 KB (960,044 bytes only for voice transcription/wake recognition), read time to ten seconds, concurrency to twenty requests per process, provider replies to 512 KB, model output to 32,000 characters, and context to ten complete turns/32,000 characters. UI/list result counts are bounded. Rate limiting is twenty auth/pairing attempts per direct client IP per minute per process, with bounded in-memory buckets. Production reverse proxies must apply their own shared limits; blindly trusting forwarded IP headers is not enabled. There are no per-account disk quotas or retention jobs yet. SQLite is intended for a small single-host service with one backend worker.

## Review findings and validation

- Cross-user chat/device/action access, approvals from another session, expired sessions, invalid/revoked device credentials, pairing/action replay, duplicate concurrent claims, forged privilege flags, command injection, and altered key ciphertext are covered by automated tests.
- Production HTTPS cookie behavior and missing encryption configuration fail-closed behavior are tested.
- A real authenticated Companion check opened Chrome, observed a new window, recorded success, and verified revocation. The full live DeepSeek-to-Chrome demo also passed on September 11, including confirmation, audit, persistence, and revocation.
- Dependency review found the cryptography 49 advisory [GHSA-g6cj-pr64-35w5](https://github.com/pyca/cryptography/security/advisories/GHSA-g6cj-pr64-35w5). The implementation uses Fernet rather than the advisory's PKCS#7 APIs, but the dependency was upgraded to patched version 50 anyway.
- This is an engineering threat review with executable checks, not an external penetration test or a claim of complete security. Review current dependency advisories and hosting controls again at public deployment.

References: [FastAPI Users database strategy](https://fastapi-users.github.io/fastapi-users/latest/configuration/authentication/strategies/database/), [cookie transport](https://fastapi-users.github.io/fastapi-users/latest/configuration/authentication/transports/cookie/), [Fernet](https://cryptography.io/en/latest/fernet/).

## V2 voice and memory review

Memory APIs require an account session and bind every query/delete/setting to that account.
The client cannot submit an owner. Writes use the existing exact-Origin/custom-header checks.
Explicit “remember” requests are validated before storing their chat turn or contacting DeepSeek;
ordinary chats are never automatically extracted into memory. Obvious credential labels, provider
key/token shapes, credential URLs, Unicode-obfuscated labels, and long mixed high-entropy strings
are rejected with fixed safe errors. This conservative detector can reject innocent text and cannot
identify every arbitrary, unlabelled secret; users must not enter secrets. Existing test sentinels
are verified absent from memory, chat rows, provider requests, and application logs.

Memories are normal database text, not application-encrypted. Delete/clear removes active records,
not backup/journal copies or separate chat messages that mentioned them. Disable blocks new saves
and future retrieval; it does not erase retained memories or facts already sent in a conversation.
A request already in progress may finish with context it retrieved before deletion/disable.
Retrieval is owner-scoped and limited to four relevant facts/1,600 characters from at most 200
records. Structured memory text is labelled data, not authority or tool permission.

Microphone access is explicit and same-origin only. Audio capture is capped at 30 seconds,
resampled to mono 16-bit/16 kHz PCM WAV, checked server-side, and held only in memory. Tracks stop
on finish/cancel/conversation switch/logout. The transcript enters the same authenticated chat
route, including device ownership and CONFIRM enforcement. A voice request itself cannot approve
a tool. TTS reads the existing response rather than generating a separate AI response. Intermediate
queued/running tool messages are not automatically synthesized; observed results drive playback.

Local CPU inference uses a fixed Python worker/module and host-configured model path, no shell
or model-specified executable/arguments. The worker receives audio/text over stdin and inherits
only minimal locale/path/offline settings, never the provider or vault keys. Models load locally;
runtime inference does not download them. One worker runs per backend process, with a bounded
two-second wait for a previous worker and 50-second execution timeout. Disconnect/cancel kills
unfinished inference and releases the slot. Outputs are bounded; stderr and raw exceptions are
suppressed. This is process isolation for cleanup and credential separation, not an OS sandbox.
Treat local model files and host administrators as trusted. Default container builds omit speech
dependencies; the opt-in voice image includes them but never includes model files or credentials.

Personality instructions allow context-sensitive warmth and light banter. Trusted confirmation,
permission, error and observed-result messages are not rewritten by the model. No browser/research,
new desktop tools or unrestricted execution has been introduced.

Wake listening is off by default and stores only an owned boolean preference. No custom keyword
is accepted. `/api/voice/wake` requires that opt-in and configured local acoustic assets, and
has no provider/chat/tool dispatch dependency. Wake is clearly labeled Beta: its known misses
and false activations are not treated as a security guarantee. The pipeline requires
an acoustic THRYV detection, locates its boundary, rejects non-invocation prefixes, and uses
unbiased local STT for the buffered command. A transcript cannot create activation. Rejected
speech never reaches DeepSeek or durable application state. Acoustic detection does not authenticate speakers
or make background speech harmless. The normal tool permission system remains the authority.

VAD keeps a short pre-roll, requires sustained sound, and ends after 1.3 seconds of silence.
One browser-origin Web Lock is held through capture, processing and playback, preventing competing
tabs from duplicating an utterance. Generation guards prevent VAD/manual-Finish/cancel races.
Wake mode pauses while processing and speaking and does not listen when the tab is hidden.
The per-account On/Off preference persists; the browser still enforces microphone permission.
