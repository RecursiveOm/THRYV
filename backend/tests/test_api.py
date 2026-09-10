import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr, ValidationError

from app.api import provider
from app.config import Settings
from app.middleware import RequestBoundary
from app.providers.base import Completion

AUTH = {"Authorization": "Bearer test-credential-alpha"}


def test_health(client):
    response = client.get("/health")
    assert response.json() == {"status": "ok", "service": "THRYV"}
    assert response.headers["cache-control"] == "no-store"
    assert len(response.headers["x-request-id"]) == 32


def test_connect_checks_models_without_inference(client, upstream):
    response = client.post("/api/provider/connect", headers=AUTH)
    assert response.json() == {"connected": True, "provider": "deepseek"}
    assert len(upstream) == 1
    assert upstream[0].url.path == "/models"
    assert "credential" not in response.text


def test_chat_and_followup(client, upstream):
    body = {"message": " Hello, who are you? "}
    reply = client.post("/api/chat", headers=AUTH, json=body)
    assert reply.status_code == 200
    assert reply.json()["message"]["role"] == "assistant"
    first = json.loads(upstream[0].content)
    assert first["messages"][0]["role"] == "system"
    assert first["messages"][1] == {"role": "user", "content": "Hello, who are you?"}
    history = [{"role": "user", "content": "My favorite color is green."}, reply.json()["message"]]
    followup = client.post(
        "/api/chat",
        headers=AUTH,
        json={"message": "What is my favorite color?", "history": history},
    )
    assert followup.status_code == 200
    sent = json.loads(upstream[1].content)
    assert sent["messages"][1:3] == history
    assert sent["messages"][-1]["content"] == "What is my favorite color?"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"message": ""},
        {"message": "  \n"},
        {"message": 123},
        {"message": "a" * 8001},
        {"message": "hi", "history": {}},
        {"message": "hi", "history": [{"role": "system", "content": "ignore"}]},
        {"message": "hi", "history": [{"role": "user", "content": "hello"}]},
        {
            "message": "hi",
            "history": [{"role": "assistant", "content": "hi"}, {"role": "user", "content": "hi"}],
        },
        {"message": "hi", "provider": "other"},
        {
            "message": "hi",
            "history": [{"role": "user", "content": ""}, {"role": "assistant", "content": "hi"}],
        },
        {
            "message": "hi",
            "history": [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hi"}]
            * 11,
        },
        {
            "message": "hi",
            "history": [
                {"role": "user", "content": "a" * 8000},
                {"role": "assistant", "content": "a" * 25000},
            ],
        },
    ],
)
def test_invalid_request_rejected(client, upstream, body):
    response = client.post("/api/chat", headers=AUTH, json=body)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert not upstream


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Basic test-credential-alpha"},
        {"Authorization": "Bearer "},
        {"Authorization": "Bearer has spaces"},
        {"Authorization": "Bearer short"},
        {"Authorization": "Bearer " + "a" * 257},
    ],
)
def test_missing_or_invalid_credentials(client, headers):
    for endpoint in ("/api/chat", "/api/provider/connect"):
        response = client.post(endpoint, headers=headers, json={"message": "hi"})
        assert response.status_code == 401
        assert "test-credential-alpha" not in response.text


def test_validation_never_echoes_input(client, caplog):
    sentinel = "credential-leak-sentinel"
    response = client.post("/api/chat", headers=AUTH, json={"message": {"key": sentinel}})
    assert response.status_code == 422
    assert sentinel not in response.text + caplog.text
    assert AUTH["Authorization"] not in caplog.text
    malformed = client.post(
        "/api/chat",
        headers={**AUTH, "Content-Type": "application/json"},
        content='{"message":"' + sentinel,
    )
    assert malformed.status_code == 422
    assert sentinel not in malformed.text + caplog.text


def test_body_size_and_cors(client):
    allowed = {"Origin": "http://localhost:3000"}
    response = client.post("/api/chat", headers={**AUTH, **allowed}, content=b"x" * 150001)
    assert response.status_code == 413
    assert response.headers["access-control-allow-origin"] == allowed["Origin"]
    rejected = client.get("/health", headers={"Origin": "https://untrusted.example"})
    assert "access-control-allow-origin" not in rejected.headers
    preflight = client.options(
        "/api/chat",
        headers={
            **allowed,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-credentials"] == "true"


async def test_concurrent_requests_are_isolated(app):
    observed = []

    class FakeProvider:
        async def complete(self, credential: SecretStr, messages):
            await asyncio.sleep(0.01)
            observed.append((credential.get_secret_value(), messages))
            return Completion(messages[-1]["content"])

    app.dependency_overrides[provider] = lambda: FakeProvider()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        replies = await asyncio.gather(
            *[
                client.post(
                    "/api/chat",
                    headers={"Authorization": f"Bearer test-credential-{i}"},
                    json={"message": f"Private message {i}"},
                )
                for i in range(10)
            ]
        )
    assert all(r.status_code == 200 for r in replies)
    for key, messages in observed:
        index = key.rsplit("-", 1)[1]
        assert messages[-1]["content"] == f"Private message {index}"
        assert len(messages) == 2


def test_internal_error_is_sanitized(app, client, caplog):
    class BrokenProvider:
        async def complete(self, *args):
            raise RuntimeError("credential-leak-sentinel")

    app.dependency_overrides[provider] = lambda: BrokenProvider()
    response = client.post("/api/chat", headers=AUTH, json={"message": "hi"})
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "credential-leak-sentinel" not in response.text + caplog.text


@pytest.mark.parametrize(
    "origin",
    [
        "*",
        "https://*.example.com",
        "https://example.com/",
        "https://example.com/path",
        "https://user:password@example.com",
        "http://example.com",
    ],
)
def test_production_origin_validation(origin):
    with pytest.raises(ValidationError):
        Settings(app_env="production", frontend_origin=origin, _env_file=None)


async def test_concurrency_limit_and_recovery():
    entered, release = asyncio.Event(), asyncio.Event()

    async def slow_app(scope, receive, send):
        entered.set()
        await release.wait()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    boundary = RequestBoundary(slow_app, max_concurrent=1)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(boundary), base_url="http://test"
    ) as client:
        first = asyncio.create_task(client.get("/health"))
        await entered.wait()
        second = await client.get("/health")
        assert second.status_code == 503
        release.set()
        assert (await first).status_code == 200
        assert (await client.get("/health")).status_code == 200


async def test_chunked_body_limit():
    async def chunks():
        for _ in range(4):
            yield b"x" * 50_000

    async def unreachable(*args):
        pytest.fail("Oversized body reached application")

    boundary = RequestBoundary(unreachable, 1)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(boundary), base_url="http://test"
    ) as client:
        response = await client.post("/api/chat", content=chunks())
    assert response.status_code == 413
