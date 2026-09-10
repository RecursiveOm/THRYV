import re
from collections.abc import AsyncIterator
from typing import Annotated

import httpx
from fastapi import APIRouter, Depends, Request
from pydantic import SecretStr

from app.errors import AppError
from app.orchestrator import Orchestrator
from app.providers.base import ChatProvider
from app.providers.deepseek import DeepSeekProvider
from app.schemas import ChatRequest, ChatResponse, ConnectionResponse

router = APIRouter()


def credential(request: Request) -> SecretStr:
    authorization = request.headers.get("authorization", "")
    scheme, _, key = authorization.partition(" ")
    if scheme.lower() != "bearer" or not key:
        raise AppError("missing_key", "Connect your DeepSeek API key to continue.", 401)
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,256}", key):
        raise AppError(
            "invalid_key", "The API key format is invalid. Check your DeepSeek key.", 401
        )
    return SecretStr(key)


async def provider(request: Request) -> AsyncIterator[ChatProvider]:
    settings = request.app.state.settings
    # Per-request clients isolate credentials and any upstream cookies between users.
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(settings.provider_timeout_seconds, connect=10),
        follow_redirects=False,
        trust_env=False,
    ) as client:
        yield DeepSeekProvider(client, settings.deepseek_model, settings.provider_timeout_seconds)


Credential = Annotated[SecretStr, Depends(credential)]
Provider = Annotated[ChatProvider, Depends(provider)]


@router.get("/health")
async def health():
    return {"status": "ok", "service": "THRYV"}


@router.post("/api/provider/connect", response_model=ConnectionResponse)
async def connect(key: Credential, runtime: Provider):
    await runtime.verify(key)
    return ConnectionResponse()


@router.post("/api/chat", response_model=ChatResponse)
async def chat(body: ChatRequest, key: Credential, runtime: Provider):
    return await Orchestrator(runtime).chat(body, key)
