import httpx
import pytest
from fastapi.testclient import TestClient

from app.api import provider
from app.config import Settings
from app.main import create_app
from app.providers.deepseek import DeepSeekProvider


@pytest.fixture
def app():
    return create_app(Settings(app_env="test", _env_file=None))


@pytest.fixture
def upstream(app):
    calls = []

    def handler(request):
        calls.append(request)
        if request.url.path == "/models":
            return httpx.Response(200, json={"data": [{"id": "deepseek-flash"}]})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {"role": "assistant", "content": "I'm THRYV, your personal AI."},
                        "finish_reason": "stop",
                    }
                ]
            },
        )

    async def override():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            yield DeepSeekProvider(client, "deepseek-flash", 1)

    app.dependency_overrides[provider] = override
    return calls


@pytest.fixture
def client(app, upstream):
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
