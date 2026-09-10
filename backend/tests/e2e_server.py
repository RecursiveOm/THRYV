"""Test-only ASGI entry point. The production entry point never imports this module."""

import json

import httpx

from app.api import provider
from app.config import Settings
from app.main import create_app
from app.providers.deepseek import DeepSeekProvider

app = create_app(Settings(app_env="test", frontend_origin="http://127.0.0.1:3001", _env_file=None))


def mock_deepseek(request: httpx.Request) -> httpx.Response:
    if request.headers["authorization"] != "Bearer test-only-valid-key":
        return httpx.Response(401, text="upstream echoed test-only-invalid-key")
    if request.url.path == "/models":
        return httpx.Response(200, json={"data": [{"id": "deepseek-flash"}]})
    messages = json.loads(request.content)["messages"]
    last = messages[-1]["content"]
    if last == "Simulate timeout":
        raise httpx.ReadTimeout("test-only-valid-key must never appear in errors")
    if last == "Show unsafe markup":
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
