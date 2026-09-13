import io
import math
import struct
import uuid
import wave

import pytest

from app.errors import AppError
from app.memory import clean_content
from app.speech import LocalSpeech
from app.voice_api import speech
from tests.test_v1 import BROWSER, action, login, pair, save_key, signup, sql, use
from tests.test_v1 import v1 as v1


def audio_bytes(seconds=1, rate=16000, channels=1):
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(channels)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(
            b"".join(
                struct.pack("<h", int(5000 * math.sin(n * 0.1)))
                for n in range(int(seconds * rate * channels))
            )
        )
    return output.getvalue()


def chat(client, message, conversation=None, device=None):
    conversation = (
        conversation or client.post("/api/conversations", headers=BROWSER, json={}).json()["id"]
    )
    response = client.post(
        f"/api/conversations/{conversation}/messages",
        headers=BROWSER,
        json={"message": message, "request_id": str(uuid.uuid4()), "device_id": device},
    )
    return conversation, response


def test_explicit_memory_survives_sessions_and_only_relevant_context(v1):
    client, _, runtime, _ = v1
    signup(client)
    save_key(client)
    _, remembered = chat(client, "Remember that I prefer Python projects to use uv.")
    assert remembered.status_code == 200
    assert "Saved to your personal memory" in remembered.text
    assert not runtime.calls  # Saving is a trusted explicit operation, not an LLM assertion.
    client.post("/api/memories", headers=BROWSER, json={"content": "My favorite tea is jasmine."})
    client.post("/api/auth/logout", headers=BROWSER)
    login(client)
    _, reply = chat(client, "What Python package workflow do I prefer?")
    assert reply.status_code == 200
    prompt = runtime.calls[-1][0]["content"]
    assert "Python projects to use uv" in prompt
    assert "jasmine" not in prompt
    assert len(client.get("/api/memories").json()["memories"]) == 2
    chat(client, "Explain why the sky is blue")
    assert "Python projects to use uv" not in runtime.calls[-1][0]["content"]
    assert len(client.get("/api/memories").json()["memories"]) == 2


def test_memory_crud_owner_isolation_clear_and_disable(v1):
    client, _, _, _ = v1
    owner = signup(client)
    first = client.post(
        "/api/memories",
        headers=BROWSER,
        json={"content": "Prefer Python with uv", "category": "preference"},
    )
    assert first.status_code == 200
    identifier = first.json()["id"]
    duplicate = client.post(
        "/api/memories", headers=BROWSER, json={"content": "Prefer Python with uv"}
    )
    assert duplicate.json()["id"] == identifier
    signup(client, "second@example.com")
    assert client.get("/api/memories").json()["memories"] == []
    assert client.delete(f"/api/memories/{identifier}", headers=BROWSER).status_code == 404
    client.delete("/api/memories", headers=BROWSER)
    use(client, owner)
    assert len(client.get("/api/memories").json()["memories"]) == 1
    assert (
        client.post("/api/memories/settings", headers=BROWSER, json={"enabled": False}).status_code
        == 200
    )
    assert (
        client.post("/api/memories", headers=BROWSER, json={"content": "Another fact"}).status_code
        == 409
    )
    save_key(client)
    _, denied = chat(client, "Remember that I like green tea")
    assert denied.status_code == 409
    assert len(client.get("/api/memories").json()["memories"]) == 1
    assert client.delete(f"/api/memories/{identifier}", headers=BROWSER).status_code == 200
    assert client.get("/api/memories").json()["memories"] == []
    client.post("/api/memories/settings", headers=BROWSER, json={"enabled": True})
    client.post(
        "/api/memories",
        headers=BROWSER,
        json={"content": "Project is THRYV", "category": "project"},
    )
    client.delete("/api/memories", headers=BROWSER)
    assert client.get("/api/memories").json()["memories"] == []


@pytest.mark.parametrize(
    "secret",
    [
        "My password is hunter2",
        "API key: sk-test-secret-value",
        "pass\u200bword is unknown",
        "Authorization Bearer abcdef",
        "access_token=short-secret",
        "-----BEGIN PRIVATE KEY-----",
        "Use https://someone:password@example.com",
        "ghp_a1b2c3d4e5f6g7h8i9j0",
        "Keep eyJhello.payload.signature",
        "Remember z9V4hB2xQ8mD1sN7aC3pK6wR",
        "hf_abcdefghijklmnopqrstuvwx",
        "github_pat_abcdefghijklmnopqrstuvwx",
        "xoxb-test-only-token",
        "Cookie: session=private-test-only-value",
    ],
)
def test_secrets_rejected_in_memory_and_not_logged_or_sent(v1, secret, caplog):
    client, path, runtime, _ = v1
    signup(client)
    save_key(client)
    assert (
        client.post("/api/memories", headers=BROWSER, json={"content": secret}).status_code == 422
    )
    _, response = chat(client, "Remember that " + secret)
    assert response.status_code == 422
    assert not sql(path, "SELECT * FROM personal_memory")
    assert not sql(path, "SELECT * FROM chat_turn")
    assert not runtime.calls
    assert secret not in response.text + caplog.text


def test_memory_csrf_and_strict_settings(v1):
    client, _, _, _ = v1
    assert client.get("/api/memories").status_code == 401
    signup(client)
    assert client.post("/api/memories", json={"content": "unsafe origin"}).status_code == 403
    assert (
        client.post(
            "/api/memories/settings", headers=BROWSER, json={"enabled": "false"}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/memories",
            headers=BROWSER,
            json={"content": "hello world", "user_id": str(uuid.uuid4())},
        ).status_code
        == 422
    )


class FakeSpeech:
    def __init__(self, text="Get system information from my paired device"):
        self.text = text

    def status(self):
        return {"stt": True, "tts": True, "local": True, "max_seconds": 30}

    async def transcribe(self, data, *, wake=False):
        return self.text

    async def wake(self, data):
        from app.wake import detect_wake

        return detect_wake(self.text)

    async def speak(self, text):
        return audio_bytes()


def test_authenticated_voice_and_audio_validation(v1):
    client, _, _, _ = v1
    client.app.dependency_overrides[speech] = lambda: FakeSpeech()
    assert client.get("/api/voice/status").status_code == 401
    signup(client)
    assert client.get("/api/voice/status").json()["local"] is True
    headers = {**BROWSER, "Content-Type": "audio/wav"}
    assert (
        client.post("/api/voice/transcribe", content=audio_bytes(), headers=headers)
        .json()["text"]
        .startswith("Get system")
    )
    for payload in (
        b"not audio",
        audio_bytes(rate=8000),
        audio_bytes(channels=2),
        audio_bytes(seconds=0.01),
    ):
        assert (
            client.post("/api/voice/transcribe", content=payload, headers=headers).status_code
            == 422
        )
    assert (
        client.post("/api/voice/transcribe", content=b"x" * 960045, headers=headers).status_code
        == 413
    )
    assert client.post("/api/voice/transcribe", content=audio_bytes()).status_code == 403
    response = client.post("/api/voice/speak", headers=BROWSER, json={"text": "Hello"})
    assert response.status_code == 200 and response.content.startswith(b"RIFF")
    assert response.headers["cache-control"] == "no-store"
    assert (
        client.post("/api/voice/speak", headers=BROWSER, json={"text": "a" * 601}).status_code
        == 422
    )


def test_voice_does_not_bypass_tool_permissions(v1):
    client, _, _, _ = v1
    signup(client)
    device, auth, _ = pair(client)
    save_key(client)
    client.app.dependency_overrides[speech] = lambda: FakeSpeech("Open Chrome on my laptop.")
    transcript = client.post(
        "/api/voice/transcribe",
        content=audio_bytes(),
        headers={**BROWSER, "Content-Type": "audio/wav"},
    ).json()["text"]
    _, response = chat(client, transcript, device=device)
    assert response.json()["action"]["permission"] == "CONFIRM"
    assert client.post("/api/companion/poll", headers=auth).json()["action"] is None
    safe = action(client, device, "get_system_info", {})
    assert safe.json()["permission"] == "SAFE"


async def test_local_speech_timeout_kills_worker_and_omits_credentials(v1, monkeypatch):
    client, _, _, _ = v1
    runtime = LocalSpeech(client.app.state.settings)
    monkeypatch.setattr(runtime, "status", lambda: {"stt": True, "tts": True})
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sensitive-test-only-key")

    class Process:
        returncode = None
        killed = False

        async def communicate(self, data):
            raise TimeoutError()

        def kill(self):
            self.killed = True

        async def wait(self):
            self.returncode = -9

    process = Process()

    async def start(*args, **kwargs):
        assert "DEEPSEEK_API_KEY" not in kwargs["env"]
        assert "CREDENTIAL_ENCRYPTION_KEY" not in kwargs["env"]
        assert args[1:3] == ("-m", "app.speech_worker")
        return process

    monkeypatch.setattr("app.speech.asyncio.create_subprocess_exec", start)
    with pytest.raises(AppError) as caught:
        await runtime.transcribe(audio_bytes())
    assert caught.value.code == "voice_timeout"
    assert process.killed and not runtime.busy


def test_memory_filter_allows_normal_durable_preferences():
    assert (
        clean_content("I prefer Python projects to use uv.")
        == "I prefer Python projects to use uv."
    )


def test_disabled_deleted_and_other_users_memories_never_enter_prompt(v1):
    client, _, runtime, _ = v1
    owner = signup(client)
    save_key(client)
    item = client.post(
        "/api/memories", headers=BROWSER, json={"content": "Python projects use uv"}
    ).json()
    client.post("/api/memories/settings", headers=BROWSER, json={"enabled": False})
    chat(client, "What Python workflow do I prefer?")
    assert "Python projects use uv" not in runtime.calls[-1][0]["content"]
    signup(client, "other-memory@example.com")
    save_key(client)
    chat(client, "What Python workflow do I prefer?")
    assert "Python projects use uv" not in runtime.calls[-1][0]["content"]
    use(client, owner)
    client.post("/api/memories/settings", headers=BROWSER, json={"enabled": True})
    client.delete("/api/memories/" + item["id"], headers=BROWSER)
    chat(client, "What Python workflow do I prefer?")
    assert "Python projects use uv" not in runtime.calls[-1][0]["content"]


def test_memory_retrieval_is_bounded_and_bare_remember_does_not_invent(v1):
    client, path, runtime, _ = v1
    signup(client)
    save_key(client)
    for n in range(6):
        client.post(
            "/api/memories",
            headers=BROWSER,
            json={"content": f"Python project {n}: " + "use uv " * 60},
        )
    chat(client, "What Python projects do I use?")
    import json

    facts = json.loads(
        runtime.calls[-1][0]["content"].split("Relevant saved user facts (JSON):\n")[1]
    )
    assert 0 < len(facts) <= 4
    assert sum(len(f["content"]) for f in facts) <= 1600
    _, response = chat(client, "Remember this")
    assert response.status_code == 422
    assert len(sql(path, "SELECT * FROM personal_memory")) == 6


async def test_voice_disconnect_cancels_pending_inference():
    import asyncio

    from app.voice_api import while_connected

    cancelled = asyncio.Event()

    class Request:
        async def receive(self):
            await asyncio.sleep(0)
            return {"type": "http.disconnect"}

    async def inference():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    with pytest.raises(AppError) as caught:
        await while_connected(Request(), inference())
    assert caught.value.code == "voice_cancelled"
    assert cancelled.is_set()


async def test_replacement_speech_waits_for_cancelled_worker_cleanup(v1, monkeypatch):
    import asyncio

    client, _, _, _ = v1
    runtime = LocalSpeech(client.app.state.settings)
    monkeypatch.setattr(runtime, "status", lambda: {"stt": True, "tts": True})
    started = asyncio.Event()
    cleaned = asyncio.Event()
    processes = []

    class Process:
        returncode = None

        async def communicate(self, data):
            if len(processes) == 1:
                started.set()
                await asyncio.Event().wait()
            self.returncode = 0
            return b"RIFF-fixture", b""

        def kill(self):
            pass

        async def wait(self):
            await asyncio.sleep(0.02)
            self.returncode = -9
            cleaned.set()

    async def start(*args, **kwargs):
        if processes:
            assert cleaned.is_set()
        process = Process()
        processes.append(process)
        return process

    monkeypatch.setattr("app.speech.asyncio.create_subprocess_exec", start)
    first = asyncio.create_task(runtime.speak("Waiting message"))
    await started.wait()
    first.cancel()
    assert await runtime.speak("Observed result") == b"RIFF-fixture"
    await asyncio.gather(first, return_exceptions=True)
    assert not runtime.busy and len(processes) == 2


@pytest.mark.parametrize(
    "phrase, command",
    [
        ("Thryv", ""),
        ("Hey Thryv", ""),
        ("Hi Thryv", ""),
        ("Okay Thryv", ""),
        ("hEy tHrYv, open Chrome", "open Chrome"),
        ("Thryv, what system am I connected to?", "what system am I connected to?"),
        ("Well, hey Thryv: open Chrome", "open Chrome"),
        ("Hey Thrive, open Chrome", "open Chrome"),
        ("Hi Thryve", ""),
    ],
)
def test_one_canonical_wake_keyword_and_same_utterance_command(phrase, command):
    from app.wake import detect_wake

    assert detect_wake(phrase) == {"detected": True, "command": command}


@pytest.mark.parametrize(
    "phrase",
    [
        "Hello there",
        "Open Chrome",
        "I heard about Thryv yesterday",
        "I want to thrive in my career",
        "Hey driver, open Chrome",
        "Okay thriving is good",
        "A television advert says hey Thryv",
        "Hey Siri",
        "Hi Alexa",
    ],
)
def test_unrelated_speech_does_not_wake(phrase):
    from app.wake import detect_wake

    assert detect_wake(phrase) == {"detected": False, "command": ""}


def test_wake_opt_in_persists_is_owned_and_cannot_dispatch_or_rename(v1):
    client, path, runtime, _ = v1
    signup(client)
    assert client.get("/api/voice/settings").json() == {
        "wake_enabled": False,
        "wake_keyword": "THRYV",
    }
    audio_headers = {**BROWSER, "Content-Type": "audio/wav"}
    client.app.dependency_overrides[speech] = lambda: FakeSpeech("Hey Thryv, open Chrome")
    assert (
        client.post("/api/voice/wake", headers=audio_headers, content=audio_bytes()).status_code
        == 409
    )
    assert client.post("/api/voice/settings", json={"wake_enabled": True}).status_code == 403
    assert (
        client.post(
            "/api/voice/settings",
            headers=BROWSER,
            json={"wake_enabled": True, "wake_keyword": "Other"},
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/voice/settings", headers=BROWSER, json={"wake_enabled": "true"}
        ).status_code
        == 422
    )
    assert (
        client.post("/api/voice/settings", headers=BROWSER, json={"wake_enabled": True}).status_code
        == 200
    )
    client.post("/api/auth/logout", headers=BROWSER)
    login(client)
    assert client.get("/api/voice/settings").json()["wake_enabled"] is True
    detected = client.post("/api/voice/wake", headers=audio_headers, content=audio_bytes())
    assert detected.json() == {"detected": True, "command": "open Chrome"}
    assert (
        not runtime.calls
        and not sql(path, "SELECT * FROM action")
        and not sql(path, "SELECT * FROM chat_turn")
    )
    signup(client, "other-voice@example.com")
    assert client.get("/api/voice/settings").json()["wake_enabled"] is False
    client.cookies.clear()
    login(client)
    client.post("/api/voice/settings", headers=BROWSER, json={"wake_enabled": False})
    assert (
        client.post("/api/voice/wake", headers=audio_headers, content=audio_bytes()).status_code
        == 409
    )
