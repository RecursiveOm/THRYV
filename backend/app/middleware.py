import asyncio
import logging
import time
from uuid import uuid4

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("thryv.requests")
MAX_BODY_BYTES = 150_000


class RequestBoundary:
    """Bound work before JSON parsing and log only controlled metadata."""

    def __init__(self, app: ASGIApp, max_concurrent: int):
        self.app = app
        self.max_concurrent = max_concurrent
        self.active = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = uuid4().hex
        status = 500
        started = time.monotonic()

        async def safe_send(message: Message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
                headers = list(message.get("headers", []))
                headers.extend(
                    [
                        (b"cache-control", b"no-store"),
                        (b"x-content-type-options", b"nosniff"),
                        (b"x-request-id", request_id.encode()),
                    ]
                )
                message = {**message, "headers": headers}
            await send(message)

        async def reject(code: str, message: str, http_status: int):
            await JSONResponse(
                {"error": {"code": code, "message": message}}, status_code=http_status
            )(scope, receive, safe_send)

        scope.setdefault("state", {})["request_id"] = request_id
        if self.active >= self.max_concurrent:
            await reject("server_busy", "THRYV is busy. Please try again shortly.", 503)
            return
        self.active += 1
        try:
            body = bytearray()
            async with asyncio.timeout(10):
                while True:
                    incoming = await receive()
                    if incoming["type"] == "http.disconnect":
                        return
                    body.extend(incoming.get("body", b""))
                    limit = (
                        960_044
                        if scope["path"] in {"/api/voice/transcribe", "/api/voice/wake"}
                        else MAX_BODY_BYTES
                    )
                    if len(body) > limit:
                        await reject(
                            "request_too_large",
                            "This request is too large. Shorten your message.",
                            413,
                        )
                        return
                    if not incoming.get("more_body", False):
                        break
            consumed = False

            async def replay():
                nonlocal consumed
                if not consumed:
                    consumed = True
                    return {"type": "http.request", "body": bytes(body), "more_body": False}
                return await receive()

            await self.app(scope, replay, safe_send)
        except TimeoutError:
            await reject(
                "request_timeout", "The request arrived too slowly. Please try again.", 408
            )
        except Exception:
            # Exception messages, traces, headers, URLs, and bodies may contain secrets.
            logger.error("request_failed request_id=%s code=internal_error", request_id)
            await reject(
                "internal_error", "THRYV couldn't complete this request. Please try again.", 500
            )
        finally:
            self.active -= 1
            logger.info(
                "request_completed request_id=%s status=%d duration_ms=%.0f",
                request_id,
                status,
                (time.monotonic() - started) * 1000,
            )
