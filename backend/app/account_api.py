import json
import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool
from sqlalchemy import delete, select, update

from app.actions import action_view, create_action, expire_actions, owned_device
from app.api import Provider
from app.auth import COOKIE_NAME, DB, Account, digest
from app.database import Action, ChatTurn, Conversation, ProviderCredential, conversation_clock, now
from app.errors import AppError
from app.memory import enabled, explicit_memory, retrieve, save
from app.orchestrator import Orchestrator, research_placeholder
from app.providers.base import Completion
from app.research import TIMEOUT, memory_query
from app.schemas import ChatRequest, Message, UserText
from app.tools import REGISTRY, validate_tool
from app.vault import decrypt_key, encrypt_key
from app.voice_api import Speech

router = APIRouter()


class ProviderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr
    consent_to_store: StrictBool


class SendMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: UserText
    request_id: uuid.UUID
    device_id: uuid.UUID | None = None


class NewConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(default="New conversation", min_length=1, max_length=120)


async def owned_conversation(db, owner, conversation_id):
    item = await db.scalar(
        select(Conversation).where(
            Conversation.id == conversation_id, Conversation.user_id == owner
        )
    )
    if item is None:
        raise AppError("not_found", "Conversation not found.", 404)
    return item


def conversation_view(item):
    return {
        "id": item.id,
        "title": item.title,
        "created_at": item.created_at,
        "updated_at": item.updated_at,
    }


@router.get("/api/account")
async def account(user: Account, db: DB):
    credential = await db.get(ProviderCredential, user.id)
    return {"id": str(user.id), "email": user.email, "provider_connected": credential is not None}


@router.post("/api/account/provider")
async def save_provider(
    body: ProviderInput, request: Request, user: Account, db: DB, runtime: Provider
):
    import re

    if not body.consent_to_store:
        raise AppError(
            "consent_required", "Confirm encrypted storage to connect this provider.", 422
        )
    if not re.fullmatch(r"[A-Za-z0-9_-]{8,256}", body.api_key.get_secret_value()):
        raise AppError("invalid_key", "Check the API key format.", 401)
    encrypted = encrypt_key(request.app.state.settings, user.id, body.api_key)
    await runtime.verify(body.api_key)
    existing = await db.get(ProviderCredential, user.id)
    if existing:
        existing.ciphertext = encrypted
    else:
        db.add(ProviderCredential(user_id=user.id, ciphertext=encrypted))
    await db.commit()
    return {"provider": "deepseek", "connected": True}


@router.delete("/api/account/provider")
async def disconnect_provider(user: Account, db: DB):
    await db.execute(delete(ProviderCredential).where(ProviderCredential.user_id == user.id))
    await db.commit()
    return {"connected": False}


@router.get("/api/account/permissions")
async def permissions(user: Account):
    return {
        "tools": [
            {"name": tool.name, "permission": tool.permission, "target": tool.target}
            for tool in REGISTRY.values()
        ],
        "unknown_tools": "BLOCKED",
    }


@router.get("/api/conversations")
async def conversations(user: Account, db: DB, offset: int = 0):
    if offset < 0 or offset > 100000:
        raise AppError("invalid_request", "Invalid page offset.", 422)
    return [
        conversation_view(c)
        for c in (
            await db.scalars(
                select(Conversation)
                .where(Conversation.user_id == user.id)
                .order_by(Conversation.updated_at.desc(), Conversation.id)
                .offset(offset)
                .limit(50)
            )
        ).all()
    ]


@router.post("/api/conversations")
async def new_conversation(body: NewConversation, user: Account, db: DB):
    item = Conversation(user_id=user.id, title=body.title)
    db.add(item)
    await db.commit()
    return conversation_view(item)


@router.get("/api/conversations/{conversation_id}")
async def get_conversation(conversation_id: uuid.UUID, user: Account, db: DB):
    item = await owned_conversation(db, user.id, str(conversation_id))
    await expire_actions(db, user.id)
    turns = list(
        (
            await db.scalars(
                select(ChatTurn)
                .where(ChatTurn.conversation_id == item.id)
                .order_by(ChatTurn.created_at.desc(), ChatTurn.id.desc())
                .limit(100)
            )
        ).all()
    )
    turns.reverse()
    messages = []
    for turn in turns:
        messages.append({"role": "user", "content": turn.user_text})
        text = (
            turn.assistant_text
            or "This request has no confirmed result. Please retry as a new message."
        )
        messages.append({"role": "assistant", "content": text})
    return {**conversation_view(item), "messages": messages}


@router.delete("/api/conversations/{conversation_id}")
async def delete_conversation(conversation_id: uuid.UUID, user: Account, db: DB):
    item = await owned_conversation(db, user.id, str(conversation_id))
    await expire_actions(db, user.id)
    if item.busy_until > now():
        raise AppError(
            "conversation_busy", "Wait for the current reply before deleting this chat.", 409
        )
    if await db.scalar(
        select(Action.id)
        .where(
            Action.conversation_id == item.id,
            Action.status.in_(["pending_confirmation", "queued", "running"]),
        )
        .limit(1)
    ):
        raise AppError(
            "conversation_busy", "Resolve the pending action before deleting this chat.", 409
        )
    await db.delete(item)
    await db.commit()
    return {"deleted": True}


@router.post("/api/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: uuid.UUID,
    body: SendMessage,
    request: Request,
    user: Account,
    db: DB,
    runtime: Provider,
    voice: Speech,
):
    item = await owned_conversation(db, user.id, str(conversation_id))
    selected_device = None
    if body.device_id:
        selected_device = await owned_device(db, user.id, str(body.device_id))
    existing = await db.scalar(
        select(ChatTurn).where(
            ChatTurn.conversation_id == item.id, ChatTurn.request_id == str(body.request_id)
        )
    )
    if existing:
        if existing.user_text != body.message:
            raise AppError("request_conflict", "This message ID has already been used.", 409)
        return {
            "message": {
                "role": "assistant",
                "content": existing.assistant_text or "This request is still being processed.",
            },
            "truncated": False,
        }
    remembered = explicit_memory(body.message)
    stored_key = await db.get(ProviderCredential, user.id)
    if stored_key is None:
        raise AppError("missing_key", "Connect your DeepSeek key in provider settings.", 409)
    key = decrypt_key(request.app.state.settings, user.id, stored_key.ciphertext)
    lease = now() + int(request.app.state.settings.provider_timeout_seconds) + TIMEOUT + 30
    claimed = await db.execute(
        update(Conversation)
        .where(Conversation.id == item.id, Conversation.busy_until <= now())
        .values(busy_until=lease)
    )
    if not claimed.rowcount:
        raise AppError(
            "conversation_busy", "Another reply is in progress in this conversation.", 409
        )
    turns = list(
        (
            await db.scalars(
                select(ChatTurn)
                .where(ChatTurn.conversation_id == item.id, ChatTurn.status == "complete")
                .order_by(ChatTurn.created_at.desc(), ChatTurn.id.desc())
                .limit(10)
            )
        ).all()
    )
    history = []
    research_requests = set(
        (
            await db.scalars(
                select(Action.request_id).where(
                    Action.conversation_id == item.id,
                    Action.user_id == user.id,
                    Action.device_id.is_(None),
                )
            )
        ).all()
    )
    remaining = 32000 - len(body.message)
    for old in turns:
        # Do not turn private planning placeholders into assistant messages for the model to echo.
        if old.request_id in research_requests or research_placeholder(old.assistant_text):
            continue
        size = len(old.user_text) + len(old.assistant_text)
        if size > remaining:
            break
        history[0:0] = [
            Message(role="user", content=old.user_text),
            Message(role="assistant", content=old.assistant_text),
        ]
        remaining -= size
    turn = ChatTurn(
        conversation_id=item.id, request_id=str(body.request_id), user_text=body.message
    )
    db.add(turn)
    await db.commit()
    action = None
    research_action = False
    truncated = False
    try:
        if remembered:
            item_memory = await save(db, user.id, *remembered)
            completion = Completion("Saved to your personal memory: " + item_memory.content)
        else:
            relevant = await retrieve(db, user.id, memory_query(body.message))
            speech_status = voice.status()
            capabilities = {
                "talk_input": bool(speech_status.get("stt")),
                "speech_output": bool(speech_status.get("tts")),
                "persistent_memory": True,
                "memory_enabled": await enabled(db, user.id),
                "public_research": True,
                "companion_online": bool(
                    selected_device
                    and not selected_device.revoked
                    and selected_device.last_seen >= now() - 15
                ),
            }
            completion = await Orchestrator(runtime).plan(
                ChatRequest(message=body.message, history=history), key, relevant, capabilities
            )
        truncated = completion.truncated
        if completion.tool_call:
            requested = REGISTRY.get(completion.tool_call.name)
            if requested and requested.target == "public_web":
                if len(request.app.state.research.tasks) >= 8:
                    raise AppError("server_busy", "Research is busy. Try again shortly.", 429)
                tool, args = validate_tool(
                    completion.tool_call.name, completion.tool_call.arguments
                )
                action = Action(
                    user_id=user.id,
                    session_hash=digest(request.cookies[COOKIE_NAME]),
                    device_id=None,
                    conversation_id=item.id,
                    request_id=str(body.request_id),
                    tool=tool.name,
                    arguments=json.dumps(args),
                    permission=tool.permission,
                    status="queued",
                    expires_at=now() + TIMEOUT + 5,
                    result_text="Starting public research…",
                )
                db.add(action)
                await db.flush()
                turn.assistant_text = action.result_text
                research_action = True
            elif not body.device_id:
                turn.assistant_text = (
                    "Select a paired device in the device picker, then ask "
                    "again. No action was executed."
                )
            else:
                try:
                    action = await create_action(
                        db,
                        user.id,
                        digest(request.cookies[COOKIE_NAME]),
                        str(body.device_id),
                        completion.tool_call.name,
                        completion.tool_call.arguments,
                        str(body.request_id),
                        item.id,
                    )
                    turn.assistant_text = Orchestrator.action_reply(
                        action.status, action.result_text
                    )
                except AppError as error:
                    turn.assistant_text = error.message + " No action was executed."
        else:
            turn.assistant_text = completion.content
        turn.status = "complete"
    except AppError:
        turn.status = "failed"
        turn.assistant_text = "The provider request failed. No action was executed."
        raise
    finally:
        await db.execute(
            update(Conversation)
            .where(Conversation.id == item.id, Conversation.busy_until == lease)
            .values(busy_until=lease if research_action else 0, updated_at=conversation_clock())
        )
        if item.title == "New conversation":
            item.title = body.message[:80]
        await db.commit()
    if research_action:
        request.app.state.research.start(action.id, key, lease)
    return {
        "message": {"role": "assistant", "content": turn.assistant_text},
        "truncated": truncated,
        "action": action_view(action) if action else None,
    }
