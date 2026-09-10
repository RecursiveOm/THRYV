import json
import secrets
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr, StrictBool
from sqlalchemy import select, update

from app.actions import (
    RESULTS,
    action_view,
    create_action,
    device_view,
    expire_actions,
    owned_device,
    sync_action_message,
)
from app.auth import COOKIE_NAME, DB, Account, digest
from app.database import Action, Device, Pairing, now
from app.errors import AppError

router = APIRouter()


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PairRequest(Strict):
    token: SecretStr
    name: str = Field(min_length=1, max_length=80, pattern=r"^[\w .-]+$")
    platform: Literal["Linux", "Windows", "Darwin"]


class ActionRequest(Strict):
    request_id: uuid.UUID
    device_id: uuid.UUID
    tool: str = Field(min_length=1, max_length=60)
    arguments: dict = Field(default_factory=dict)


class Decision(Strict):
    allow: StrictBool


class Result(Strict):
    code: Literal[
        "application_opened",
        "application_missing",
        "launch_failed",
        "launch_unconfirmed",
        "unsupported_platform",
        "system_info",
        "timeout",
        "blocked",
        "execution_uncertain",
    ]
    platform: Literal["Linux", "Windows", "Darwin"] | None = None
    architecture: Literal["x86_64", "aarch64", "arm64", "unknown"] | None = None


async def authenticated_device(request: Request, db: DB):
    header = request.headers.get("authorization", "")
    if not header.startswith("Bearer ") or len(header) > 300:
        raise AppError("device_unauthenticated", "Companion must pair again.", 401)
    device = await db.scalar(
        update(Device)
        .where(Device.token_hash == digest(header[7:]), Device.revoked.is_(False))
        .values(last_seen=Device.last_seen)
        .returning(Device)
    )
    if device is None:
        raise AppError(
            "device_unauthenticated", "Companion credentials are invalid or revoked.", 401
        )
    return device


Companion = Annotated[Device, Depends(authenticated_device)]


@router.get("/api/devices")
async def devices(user: Account, db: DB):
    return [
        device_view(d)
        for d in (
            await db.scalars(
                select(Device)
                .where(Device.user_id == user.id)
                .order_by(Device.created_at.desc())
                .limit(100)
            )
        ).all()
    ]


@router.post("/api/devices/pairing")
async def pairing(user: Account, db: DB):
    # 256 random bits; only a digest persists. The token is an account-bound capability.
    raw = secrets.token_urlsafe(32)
    db.add(Pairing(token_hash=digest(raw), user_id=user.id, expires_at=now() + 300))
    await db.commit()
    return {"token": raw, "expires_in": 300}


@router.post("/api/companion/pair")
async def pair(body: PairRequest, db: DB):
    raw = body.token.get_secret_value()
    if len(raw) != 43:
        raise AppError("invalid_pairing", "Pairing token is invalid or expired.", 400)
    claimed = await db.execute(
        update(Pairing)
        .where(
            Pairing.token_hash == digest(raw), Pairing.used.is_(False), Pairing.expires_at > now()
        )
        .values(used=True)
        .returning(Pairing.user_id)
    )
    owner = claimed.scalar_one_or_none()
    if owner is None:
        raise AppError(
            "invalid_pairing", "Pairing token is invalid, expired, or already used.", 400
        )
    credential = secrets.token_urlsafe(32)
    device = Device(
        user_id=owner,
        name=body.name.strip(),
        platform=body.platform,
        token_hash=digest(credential),
        last_seen=now(),
    )
    db.add(device)
    await db.commit()
    return {"device_id": device.id, "credential": credential}


@router.delete("/api/devices/{device_id}")
async def revoke(device_id: uuid.UUID, user: Account, db: DB):
    device = await owned_device(db, user.id, str(device_id))
    device.revoked = True
    pending = (
        await db.scalars(
            select(Action).where(
                Action.device_id == device.id,
                Action.status.in_(["pending_confirmation", "queued", "running"]),
            )
        )
    ).all()
    for action in pending:
        action.status = "cancelled"
        action.result_code = "revoked"
        action.result_text = RESULTS["revoked"]
        await sync_action_message(db, action)
    await db.commit()
    return {"revoked": True}


@router.get("/api/actions")
async def actions(user: Account, db: DB):
    await expire_actions(db, user.id)
    return [
        action_view(a)
        for a in (
            await db.scalars(
                select(Action)
                .where(Action.user_id == user.id)
                .order_by(Action.created_at.desc(), Action.id)
                .limit(100)
            )
        ).all()
    ]


@router.post("/api/actions")
async def request_action(body: ActionRequest, request: Request, user: Account, db: DB):
    action = await create_action(
        db,
        user.id,
        digest(request.cookies[COOKIE_NAME]),
        str(body.device_id),
        body.tool,
        body.arguments,
        str(body.request_id),
    )
    await db.commit()
    return action_view(action)


@router.post("/api/actions/{action_id}/decision")
async def decision(action_id: uuid.UUID, body: Decision, request: Request, user: Account, db: DB):
    action = await db.scalar(
        select(Action).where(Action.id == str(action_id), Action.user_id == user.id)
    )
    if action is None:
        raise AppError("not_found", "Action not found.", 404)
    if action.session_hash != digest(request.cookies[COOKIE_NAME]):
        raise AppError(
            "confirmation_session", "Approve this action in the session that requested it.", 403
        )
    device = await owned_device(db, user.id, action.device_id)
    if device.revoked or (body.allow and device.last_seen < now() - 15):
        raise AppError("device_offline", "The device is unavailable. No action was approved.", 409)
    status = "queued" if body.allow else "cancelled"
    result = await db.execute(
        update(Action)
        .where(
            Action.id == action.id,
            Action.status == "pending_confirmation",
            Action.expires_at > now(),
        )
        .values(status=status, expires_at=now() + 30)
    )
    if not result.rowcount:
        raise AppError(
            "confirmation_expired", "This confirmation expired or was already used.", 409
        )
    await db.refresh(action)
    await sync_action_message(db, action)
    await db.commit()
    return action_view(action)


@router.post("/api/companion/poll")
async def poll(device: Companion, db: DB):
    await expire_actions(db, device.user_id)
    heartbeat = await db.execute(
        update(Device)
        .where(Device.id == device.id, Device.revoked.is_(False))
        .values(last_seen=now())
    )
    if not heartbeat.rowcount:
        raise AppError("device_unauthenticated", "Device is revoked.", 401)
    action = await db.scalar(
        select(Action)
        .where(
            Action.device_id == device.id,
            Action.user_id == device.user_id,
            Action.status == "queued",
            Action.expires_at > now(),
        )
        .order_by(Action.created_at)
        .limit(1)
    )
    if action:
        claimed = await db.execute(
            update(Action)
            .where(Action.id == action.id, Action.status == "queued", Action.expires_at > now())
            .values(status="running")
        )
        if claimed.rowcount:
            await db.commit()
            return {
                "action": {
                    "id": action.id,
                    "tool": action.tool,
                    "arguments": json.loads(action.arguments),
                    "expires_at": action.expires_at,
                }
            }
    await db.commit()
    return {"action": None}


@router.post("/api/companion/actions/{action_id}/authorize")
async def authorize_execution(action_id: uuid.UUID, device: Companion, db: DB):
    action = await db.scalar(
        select(Action).where(
            Action.id == str(action_id),
            Action.device_id == device.id,
            Action.user_id == device.user_id,
            Action.status == "running",
            Action.expires_at > now(),
        )
    )
    if action is None:
        raise AppError("action_unavailable", "This action is no longer authorized.", 409)
    return {"authorized": True}


@router.post("/api/companion/actions/{action_id}/result")
async def execution_result(action_id: uuid.UUID, body: Result, device: Companion, db: DB):
    action = await db.scalar(
        select(Action).where(
            Action.id == str(action_id),
            Action.device_id == device.id,
            Action.user_id == device.user_id,
        )
    )
    if action is None:
        raise AppError("not_found", "Action not found.", 404)
    expected_success = "application_opened" if action.tool == "open_application" else "system_info"
    if body.code in ("application_opened", "system_info") and body.code != expected_success:
        raise AppError("invalid_result", "Result does not match the requested tool.", 422)
    text = RESULTS[body.code]
    if body.code == "system_info":
        text = f"Device reports {body.platform or 'unknown OS'} ({body.architecture or 'unknown'})."
    result = await db.execute(
        update(Action)
        .where(Action.id == action.id, Action.status == "running", Action.expires_at > now())
        .values(
            status="succeeded" if body.code == expected_success else "failed",
            result_code=body.code,
            result_text=text,
        )
    )
    if not result.rowcount:
        raise AppError(
            "action_unavailable", "This action expired or its result was already recorded.", 409
        )
    await db.refresh(action)
    await sync_action_message(db, action)
    await db.commit()
    return {"recorded": True}
