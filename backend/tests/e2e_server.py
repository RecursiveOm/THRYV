"""Test-only ASGI entry point. The production entry point never imports this module."""

import json
import tempfile
from pathlib import Path

import httpx
from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet

from app.api import provider
from app.config import Settings
from app.main import create_app
from app.providers.deepseek import DeepSeekProvider
from app.voice_api import speech
from tests.test_v2 import FakeSpeech

_directory = tempfile.TemporaryDirectory(prefix="thryv-browser-tests-")
_url = f"sqlite+aiosqlite:///{_directory.name}/test.db"
_migration = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
_migration.attributes["database_url"] = _url
command.upgrade(_migration, "head")
app = create_app(
    Settings(
        app_env="test",
        frontend_origin="http://127.0.0.1:3001",
        database_url=_url,
        credential_encryption_key=Fernet.generate_key().decode(),
        auth_attempts_per_minute=1000,
        _env_file=None,
    )
)


def mock_deepseek(request: httpx.Request) -> httpx.Response:
    if request.headers["authorization"] != "Bearer test-only-valid-key":
        return httpx.Response(401, text="upstream echoed test-only-invalid-key")
    if request.url.path == "/models":
        return httpx.Response(200, json={"data": [{"id": "deepseek-flash"}]})
    messages = json.loads(request.content)["messages"]
    last = messages[-1]["content"]
    if last in ("Open Chrome on my laptop.", "Get system information from my paired device"):
        tool = "open_application" if last.startswith("Open") else "get_system_info"
        args = '{"application":"chrome"}' if tool == "open_application" else "{}"
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "I already opened it (untrusted text)",
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": tool,
                                        "arguments": args,
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        )
    if last == "Simulate timeout":
        raise httpx.ReadTimeout("test-only-valid-key must never appear in errors")
    if last == "What Python package workflow do I prefer?":
        answer = (
            "You prefer uv for Python projects."
            if "Python projects to use uv" in messages[0]["content"]
            else "I have no saved preference."
        )
    elif last == "Show unsafe markup":
        answer = (
            '<script>alert("unsafe")</script>\n\n[bad link](javascript:alert(1))\n\n'
            "![tracking](https://tracker.invalid/image)\n\n**Safe formatting**"
        )
    elif len(messages) > 2:
        answer = "You told me: " + messages[1]["content"]
    else:
        answer = "I'm **THRYV**, your personal AI. What can I help you with?"
    return httpx.Response(
        200,
        json={
            "choices": [
                {"message": {"role": "assistant", "content": answer}, "finish_reason": "stop"}
            ]
        },
    )


async def test_provider():
    async with httpx.AsyncClient(transport=httpx.MockTransport(mock_deepseek)) as client:
        yield DeepSeekProvider(client, "deepseek-flash", 1)


app.dependency_overrides[provider] = test_provider

app.dependency_overrides[speech] = lambda: FakeSpeech()
