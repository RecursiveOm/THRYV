# V3 verification — September 13–14, 2026

Branch: `feat/thryv-v3`, based on pushed V2 commit
`ec0e841124b0c054fa1571f996182e04b4974be5` (`feat/thryv-v2`).
Engineering model verified from session metadata: GPT-6 Astra. No subagents.

## Automated checks

Focused gate: **32 backend V3 tests**, **4 browser V3 cases** across desktop/mobile,
and **11 focused Companion cases** passed. Follow-up checks covered escaped source citations
and rejecting a result from the wrong paired device. Ordinary tests mock provider responses,
public pages and desktop effects.

The complete V0/V1/V2/V3 regression suite ran once after focused checks:

| Suite | Result |
| --- | --- |
| Backend | **184 passed**, 2 upstream Starlette/AnyIO deprecation warnings |
| Browser | **58 passed**, desktop/mobile Chromium |
| Companion | **31 passed** |
| Backend and Companion Ruff lint/format | Passed |
| Frontend ESLint and TypeScript | Passed |
| Frontend production build | Passed |
| Locked backend/Companion sync and frontend npm ci | Passed |
| Backend/Companion pip-audit, frontend moderate-level npm audit | No known dependency vulnerabilities |
| Alembic upgrade and drift check | Passed; revision `37d6a04b213a` |
| V3 default backend Docker build | Passed |
| Disposable production container smoke | Passed: non-root migration, private data modes, health, schema, artifact exclusion and migration consistency |

The unpublished Companion package itself cannot be audited against PyPI; its dependencies were
audited. ESLint emitted an upstream Node url.parse() deprecation warning. The V3 Docker build
used the default image without voice extras. V2's voice-enabled image checks are preserved in
[its report](verification-v2.md); speech also ran live on the V3 host.

Coverage includes unsafe URLs, mixed public/private DNS answers, DNS pinning, private redirects,
redirect loops, compressed/oversized bodies, HTML extraction/links/metadata, typed permissions,
owned navigation, duplicate suppression, cancellation, logout, timeout, step limits, forged
citations, page injection, relevant memory/no autosave, local confirmation/device isolation/audit,
and final-answer-only voice TTS.

Final diff review added an HTML nesting bound against pathological parser work. Its existing
focused extraction/security case passed again, and the backend image/container smoke were
rebuilt/rechecked for that change. The full regression suite was not repeated.

## Live acceptance (automated interactions, real services)

These are live engineering checks, not a human microphone/listening study. Scripts disable
traces/screenshots, suppress raw errors/responses and credentials, and remove saved test keys,
memories, Companion credentials and temporary audio afterward.

- **LangGraph persistence:** actual search and official page retrieval, including
  https://docs.langchain.com/oss/python/langgraph/persistence; real DeepSeek synthesis and
  captured source metadata. Retrieved content included checkpoint/persistence guidance.
- **Memory-aware speech research:** saved a free/open-source tool preference, started a new
  conversation, researched speech-recognition options, retrieved official Whisper and
  faster-whisper GitHub pages, and observed the preference in the grounded answer.
- **Local FastAPI website:** real paired Linux Companion; open_url stayed pending CONFIRM
  until approval, then observed a new Chrome window and recorded url_opened. Page loading
  was explicitly not claimed as verified.
- **Controlled injection:** malicious HTML parsed through the extractor and synthesized by real
  DeepSeek. The fixture requested secret disclosure and extra tools; synthesis had no tool
  interface or credential values and retained legitimate HTTPS/health-check guidance. This
  controlled fixture did not require hosting a malicious public site.
- **Voice research:** synthetic microphone WAV → browser Talk → VAD → actual faster-whisper →
  existing orchestrator → live FastAPI deployment/concepts pages → grounded answer →
  actual Piper synthesis → browser Speaking state after playback started → Stop.

One memory-research attempt received provider_response and safely executed no action.
The planning instruction was clarified to request one combined research tool; the remaining
demos passed. The first voice harness looked for a DOM audio element, although playback uses
a detached Audio object; research had succeeded. The harness now checks the actual Speaking
state, and the focused live voice rerun passed. Completed demos were not repeated.

## Review and limitations

Diff/security review covered credential separation, ownership, public DNS/redirect restrictions,
no private browser cookies, tool-free synthesis, excluding research text from later tool planning,
escaped source links, cancellation guards, Companion confirmation/replay and V2 voice preservation.
Local secrets remain ignored; exact configured secret values were checked against files prepared
for commit. This is an engineering review, not an external penetration test.

Public browsing is GET-only structured HTML/text, not a JavaScript browser. Search relevance and
provider responses vary; explicit official URLs are supported. No login, PDF, forms, uploads,
CAPTCHA bypass or arbitrary JavaScript. Source validation cannot guarantee every model
interpretation. Snapshots/audit excerpts persist as normal owned database text. One backend
process is supported. Wake remains off-by-default Beta with known misses/similar-word false
activations; no tuning occurred. No physical-microphone manual test, public deployment, V4
feature or private authenticated browser automation is claimed.

## Preserved milestones

[V2 verification](verification-v2.md): **152 backend / 54 browser / 22 Companion** passed,
with live memory persistence/deletion, Talk SAFE/CONFIRM and Beta one-shot confirmation.
V2's held-out wake result was **8/12 combined cases**, including three misses and one Drive
false activation; it is not positive-only recall. Talk remains the recommended fallback.
[V1 verification](verification-v1.md) and [V0 verification](verification-v0.md) preserve their
historical evidence. V0/V1/V2 regressions passed in the V3 totals above.
