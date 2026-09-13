import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy import update

from app.auth import DB, Account
from app.database import User, VoiceSetting
from app.errors import AppError
from app.speech import MAX_AUDIO_BYTES, LocalSpeech, validate_audio

router = APIRouter()


def speech(request: Request):
    return request.app.state.speech


Speech = Annotated[LocalSpeech, Depends(speech)]


async def while_connected(request, operation):
    async def disconnected():
        while (await request.receive())["type"] != "http.disconnect":
            pass

    work = asyncio.create_task(operation)
    watcher = asyncio.create_task(disconnected())
    try:
        await asyncio.wait({work, watcher}, return_when=asyncio.FIRST_COMPLETED)
        if work.done():
            return work.result()
        raise AppError("voice_cancelled", "Voice request cancelled.", 499)
    finally:
        work.cancel()
        watcher.cancel()
        await asyncio.gather(work, watcher, return_exceptions=True)


class SpeakInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    text: str = Field(min_length=1, max_length=600)


@router.get("/api/voice/status")
async def status(user: Account, runtime: Speech):
    return runtime.status()


async def read_audio(request: Request):
    if request.headers.get("content-type", "").split(";")[0] != "audio/wav":
        raise AppError("invalid_audio", "Use a WAV voice recording.", 422)
    data = await request.body()
    if len(data) > MAX_AUDIO_BYTES:
        raise AppError("invalid_audio", "Voice recordings are limited to 30 seconds.", 413)
    validate_audio(data)
    return data


@router.post("/api/voice/transcribe")
async def transcribe(request: Request, user: Account, runtime: Speech):
    data = await read_audio(request)
    return {"text": await while_connected(request, runtime.transcribe(data))}


@router.post("/api/voice/speak")
async def speak(body: SpeakInput, request: Request, user: Account, runtime: Speech):
    data = await while_connected(request, runtime.speak(body.text))
    return Response(content=data, media_type="audio/wav")


class VoicePreferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    wake_enabled: StrictBool


@router.get("/api/voice/settings")
async def preferences(user: Account, db: DB):
    item = await db.get(VoiceSetting, user.id)
    return {"wake_enabled": bool(item and item.wake_enabled), "wake_keyword": "THRYV"}


@router.post("/api/voice/settings")
async def update_preferences(body: VoicePreferences, user: Account, db: DB):
    await db.execute(update(User).where(User.id == user.id).values(is_active=User.is_active))
    item = await db.get(VoiceSetting, user.id)
    if item:
        item.wake_enabled = body.wake_enabled
    else:
        db.add(VoiceSetting(user_id=user.id, wake_enabled=body.wake_enabled))
    await db.commit()
    return {"wake_enabled": body.wake_enabled, "wake_keyword": "THRYV"}


@router.post("/api/voice/wake")
async def wake(request: Request, user: Account, db: DB, runtime: Speech):
    item = await db.get(VoiceSetting, user.id)
    if not item or not item.wake_enabled:
        raise AppError("wake_disabled", "Enable wake-word listening in Voice settings first.", 409)
    try:
        data = await read_audio(request)
        result = await while_connected(request, runtime.wake(data))
    except AppError as error:
        if error.code == "no_speech":
            return {"detected": False, "command": ""}
        raise
    # This endpoint cannot access the provider, save a chat, or dispatch a tool.
    return result
