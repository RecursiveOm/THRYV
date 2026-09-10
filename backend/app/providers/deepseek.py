import asyncio
import json

import httpx
from pydantic import SecretStr

from app.errors import AppError
from app.providers.base import Completion, ProviderMessage, ToolCall
from app.schemas import MAX_REPLY_CHARS

BASE_URL = "https://api.deepseek.com"
MAX_RESPONSE_BYTES = 512_000


class DeepSeekProvider:
    def __init__(self, client: httpx.AsyncClient, model: str, timeout: float):
        self.client = client
        self.model = model
        self.timeout = timeout

    async def _request(self, method: str, path: str, credential: SecretStr, **kwargs):
        try:
            # A wall-clock deadline also bounds slow keepalive/whitespace responses.
            async with asyncio.timeout(self.timeout):
                async with self.client.stream(
                    method,
                    BASE_URL + path,
                    headers={"Authorization": f"Bearer {credential.get_secret_value()}"},
                    **kwargs,
                ) as response:
                    self._check_status(response.status_code)
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > MAX_RESPONSE_BYTES:
                            raise AppError(
                                "provider_response", "DeepSeek returned an oversized response."
                            )
                    return json.loads(body)
        except (TimeoutError, httpx.TimeoutException):
            pass
        except httpx.RequestError:
            raise AppError(
                "provider_unavailable", "THRYV couldn't reach DeepSeek. Please try again."
            ) from None
        except (ValueError, UnicodeError):
            raise AppError(
                "provider_response", "DeepSeek returned an unreadable response. Please try again."
            ) from None
        raise AppError(
            "provider_timeout", "DeepSeek took too long to respond. Please try again.", 504
        )

    @staticmethod
    def _check_status(status: int) -> None:
        # Provider error bodies can echo keys. Never parse, return, or log them.
        if status in (401, 403):
            raise AppError(
                "invalid_key", "DeepSeek didn't accept this API key. Check or replace it.", 401
            )
        if status == 402:
            raise AppError("insufficient_balance", "Your DeepSeek account needs API credit.", 402)
        if status == 429:
            raise AppError(
                "rate_limited", "DeepSeek is rate limiting requests. Wait a moment and retry.", 429
            )
        if status >= 500:
            raise AppError(
                "provider_unavailable", "DeepSeek is temporarily unavailable. Try again soon.", 503
            )
        if status != 200:
            raise AppError(
                "provider_rejected", "DeepSeek couldn't process this request. Please try again."
            )

    async def verify(self, credential: SecretStr) -> None:
        payload = await self._request("GET", "/models", credential)
        if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
            raise AppError("provider_response", "DeepSeek returned an invalid connection response.")
        if not any(isinstance(m, dict) and m.get("id") == self.model for m in payload["data"]):
            raise AppError(
                "model_unavailable",
                "The configured DeepSeek model is unavailable. Contact the THRYV host.",
                503,
            )

    async def complete(self, credential: SecretStr, messages: list[ProviderMessage]) -> Completion:
        return await self._complete(credential, messages)

    async def plan(self, credential: SecretStr, messages, tools) -> Completion:
        return await self._complete(credential, messages, tools)

    async def _complete(self, credential, messages, tools=None) -> Completion:
        payload = await self._request(
            "POST",
            "/chat/completions",
            credential,
            json={
                "model": self.model,
                "messages": messages,
                "thinking": {"type": "disabled"},
                "stream": False,
                "max_tokens": 4096,
                **({"tools": tools, "tool_choice": "auto"} if tools else {}),
            },
        )
        try:
            choice = payload["choices"][0]
            message = choice["message"]
            content = message.get("content")
            finish = choice["finish_reason"]
            if tools and finish == "tool_calls":
                calls = message.get("tool_calls", [])
                if (
                    message.get("role") != "assistant"
                    or not isinstance(calls, list)
                    or len(calls) != 1
                    or not isinstance(calls[0], dict)
                    or calls[0].get("type") != "function"
                ):
                    raise ValueError("Only one tool call is allowed")
                function = calls[0]["function"]
                arguments = json.loads(function["arguments"])
                if not isinstance(arguments, dict) or not isinstance(function["name"], str):
                    raise ValueError("Malformed tool call")
                return Completion("", tool_call=ToolCall(function["name"], arguments))
            if finish == "content_filter":
                raise AppError(
                    "content_filtered",
                    "DeepSeek couldn't answer this request. Try rephrasing it.",
                    422,
                )
            if (
                message.get("role") != "assistant"
                or message.get("tool_calls")
                or finish not in ("stop", "length")
                or not isinstance(content, str)
                or not content.strip()
                or len(content) > MAX_REPLY_CHARS
            ):
                raise ValueError("Invalid completion")
            return Completion(content=content.strip(), truncated=finish == "length")
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            raise AppError(
                "provider_response", "DeepSeek returned an incomplete response. Please try again."
            ) from None
