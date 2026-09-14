import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.errors import AppError
from app.orchestrator import SYSTEM_PROMPT, Orchestrator
from app.providers.base import Completion
from app.providers.deepseek import DeepSeekProvider
from app.schemas import ChatRequest

KEY = SecretStr("test-credential-sentinel")
MESSAGES = [{"role": "user", "content": "Hi"}]


async def complete_with(response):
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: response)) as client:
        return await DeepSeekProvider(client, "deepseek-flash", 1).complete(KEY, MESSAGES)


@pytest.mark.parametrize(
    ("status", "code", "http_status"),
    [
        (401, "invalid_key", 401),
        (403, "invalid_key", 401),
        (402, "insufficient_balance", 402),
        (429, "rate_limited", 429),
        (500, "provider_unavailable", 503),
        (503, "provider_unavailable", 503),
        (400, "provider_rejected", 502),
        (422, "provider_rejected", 502),
        (302, "provider_rejected", 502),
    ],
)
async def test_provider_error_mapping(status, code, http_status, caplog):
    with pytest.raises(AppError) as caught:
        await complete_with(httpx.Response(status, text=KEY.get_secret_value()))
    assert caught.value.code == code
    assert caught.value.status == http_status
    assert KEY.get_secret_value() not in str(caught.value) + caught.value.message + caplog.text


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        [],
        {"choices": []},
        {"choices": [None]},
        {"choices": [{"message": None}]},
        {"choices": [{"message": {"role": "assistant", "content": ""}, "finish_reason": "stop"}]},
        {"choices": [{"message": {"role": "assistant", "content": 42}, "finish_reason": "stop"}]},
        {
            "choices": [
                {
                    "message": {"role": "assistant", "content": "hello"},
                    "finish_reason": "tool_calls",
                }
            ]
        },
    ],
)
async def test_malformed_completions(payload):
    with pytest.raises(AppError, match="provider_response"):
        await complete_with(httpx.Response(200, json=payload))


async def test_invalid_json_and_oversized_response():
    for response in [
        httpx.Response(200, text="not JSON"),
        httpx.Response(200, content=b"x" * 512001),
    ]:
        with pytest.raises(AppError, match="provider_response"):
            await complete_with(response)


@pytest.mark.parametrize("exception", [httpx.ConnectError("secret"), httpx.ReadTimeout("secret")])
async def test_network_failure(exception):
    def fail(request):
        raise exception

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail)) as client:
        with pytest.raises(AppError) as caught:
            await DeepSeekProvider(client, "deepseek-flash", 1).complete(KEY, MESSAGES)
    assert caught.value.code in ("provider_timeout", "provider_unavailable")
    assert "secret" not in caught.value.message


async def test_wall_clock_deadline():
    async def slow(request):
        await asyncio.sleep(1)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(slow)) as client:
        with pytest.raises(AppError, match="provider_timeout"):
            await DeepSeekProvider(client, "deepseek-flash", 0.01).complete(KEY, MESSAGES)


async def test_request_contract_and_truncation():
    def handler(request):
        assert request.url == "https://api.deepseek.com/chat/completions"
        assert request.headers["authorization"] == f"Bearer {KEY.get_secret_value()}"
        payload = json.loads(request.content)
        assert KEY.get_secret_value() not in request.url.query.decode() + request.content.decode()
        assert payload == {
            "model": "deepseek-flash",
            "messages": MESSAGES,
            "thinking": {"type": "disabled"},
            "stream": False,
            "max_tokens": 4096,
        }
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": " hello ",
                            "reasoning_content": "private reasoning",
                        },
                        "finish_reason": "length",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await DeepSeekProvider(client, "deepseek-flash", 1).complete(KEY, MESSAGES)
    assert result == Completion("hello", truncated=True)


@pytest.mark.parametrize(
    "payload", [{}, {"data": None}, {"data": []}, {"data": [{"id": "unavailable"}]}]
)
async def test_invalid_model_connection(payload):
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as client:
        with pytest.raises(AppError):
            await DeepSeekProvider(client, "deepseek-flash", 1).verify(KEY)


async def test_orchestrator_uses_protocol_and_preserves_identity():
    class FakeProvider:
        async def complete(self, credential, messages):
            assert credential is KEY
            assert messages[0] == {"role": "system", "content": SYSTEM_PROMPT}
            assert messages[1] == {"role": "user", "content": "Hello"}
            assert "Omkar" not in SYSTEM_PROMPT
            assert "no tools" in SYSTEM_PROMPT
            return Completion("I'm THRYV.")

    result = await Orchestrator(FakeProvider()).chat(ChatRequest(message="Hello"), KEY)
    assert result.message.content == "I'm THRYV."


@pytest.mark.parametrize(
    "calls",
    [
        None,
        [],
        ["bad"],
        [{"type": "function", "function": None}],
        [{"type": "function", "function": {"name": "open_application", "arguments": "not JSON"}}],
        [{"type": "function", "function": {"name": "open_application", "arguments": "[]"}}],
        [{"type": "function"}, {"type": "function"}],
    ],
)
async def test_malformed_structured_calls_fail_closed(calls):
    payload = {
        "choices": [
            {"message": {"role": "assistant", "tool_calls": calls}, "finish_reason": "tool_calls"}
        ]
    }
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    ) as client:
        with pytest.raises(AppError) as caught:
            await DeepSeekProvider(client, "deepseek-flash", 1).plan(
                KEY, MESSAGES, [{"type": "function"}]
            )
        assert caught.value.code == "provider_response"


async def test_structured_request_discards_untrusted_success_text():
    from app.tools import REGISTRY

    def handler(request):
        body = json.loads(request.content)
        assert body["tool_choice"] == "auto"
        assert {tool["function"]["name"] for tool in body["tools"]} == set(REGISTRY)
        assert body["thinking"] == {"type": "disabled"}
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "I already opened it",
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": "open_application",
                                        "arguments": '{"application":"chrome"}',
                                    },
                                }
                            ],
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await DeepSeekProvider(client, "deepseek-flash", 1).plan(
            KEY, MESSAGES, [t.definition() for t in REGISTRY.values()]
        )
    assert result.content == ""
    assert result.tool_call.name == "open_application"
    assert result.tool_call.arguments == {"application": "chrome"}
