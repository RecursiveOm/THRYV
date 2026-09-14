# THRYV V2 verification

Date: September 13, 2026. Engineering model: GPT-6 Astra, verified from session metadata.
Branch: `feat/thryv-v2`. V2 passes the user's revised Beta acceptance policy. No public
deployment was performed. V3 implementation begins only after this milestone is pushed.

## Automated regression

The full suite ran once after focused V2 checks passed (60 backend and 16 voice/wake browser
checks). Final counts: **152 backend, 54 desktop/mobile browser, 22 Companion tests passed**.
Tests cover V0/V1 regression, owned memory/settings, secret rejection, VAD, Finish/Cancel,
microphone cleanup, repeated interactions, single-tab ownership, and confirmed single execution.
Ordinary tests mock provider and desktop side effects.

- Backend/Companion lint, format, locked dependency sync and dependency audits passed.
- Frontend clean install, lint, TypeScript, production build and dependency audit passed.
- Alembic reported no metadata drift; migration tests passed.
- Voice-enabled Docker build passed. Disposable-container checks passed for non-root migration,
  production health, private data permissions, schema, artifact exclusion and migration consistency.
- Only two upstream Starlette/AnyIO test deprecation warnings remain. The unpublished local
  Companion package itself is skipped by pip-audit; its dependencies were audited.

## Live acceptance

Opt-in scripts used locally supplied credentials, real DeepSeek, actual local speech engines,
Chromium microphone capture with synthetic WAV input, and the real Linux Companion:

- Explicit memory → new conversation recall → logout/login recall passed. Deletion → empty
  memory list → new conversation without a claimed saved preference passed.
- Talk → VAD auto-finish → STT → SAFE system-info → observed device result → TTS playback/Stop passed.
- Talk “Open Chrome” → CONFIRM → actual Chrome window → observed result → TTS passed.
- Beta “Hey Thryv, open Chrome” completed the same confirmed one-shot flow and TTS.
- Technical, casual and playful live replies passed bounded-content sanity checks. These are
  not a human qualitative personality evaluation.
- Scripts removed saved keys, revoked test devices, disabled wake, signed out and removed
  temporary credentials/audio. No traces, screenshots, raw replies or credentials were recorded
  in validation artifacts.

## Wake Beta limitations and security review

Wake is explicitly Beta, fixed to THRYV, off by default and stored per authenticated user.
Talk remains the recommended reliable fallback. Historical held-out acoustic evaluation passed
**8/12 combined cases**, not 8/12 positive-only recall: three missed invocations and one “Drive”
false activation. This limitation is accepted for Beta; no further tuning occurred in this
release run. The [model card](../backend/app/models/README.md) records training and validation.

Human microphone/accent/noisy-room reliability was not tested. A false wake may start listening
or submit a transcription; it cannot bypass SAFE/CONFIRM/BLOCKED policy. Chrome remains CONFIRM.
The wake endpoint cannot call DeepSeek, save chat/memory, or dispatch tools by itself. Passive
audio stays in bounded local processing and is not persisted or continuously sent to an LLM.

Reviewed ownership predicates, CSRF enforcement, explicit memory/secret filtering, bounded
credential-free speech workers, microphone lifecycle and confirmation routing. Exact locally
configured secret values were absent from tracked/new source, and `.env` files remain untracked.
Memory deletion stops future retrieval; it does not erase text already present in old chats.

Historical evidence: [V1](verification-v1.md), [V0](verification-v0.md).
