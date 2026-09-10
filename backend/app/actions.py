import json

from sqlalchemy import select, update

from app.database import Action, ChatTurn, Device, now
from app.errors import AppError
from app.tools import validate_tool

TERMINAL = {"succeeded", "failed", "cancelled", "expired"}
RESULTS = {
    "application_opened": "The application window opened on your device.",
    "application_missing": "The application is not installed on this device.",
    "launch_failed": "The application could not be launched.",
    "launch_unconfirmed": (
        "The launch was requested, but an application window could not be verified."
    ),
    "unsupported_platform": "This Companion cannot perform that action on this platform.",
    "system_info": "Basic system information was received from your device.",
    "timeout": "The device did not confirm execution before the deadline. The outcome is unknown.",
    "blocked": "Companion blocked this action.",
    "execution_uncertain": (
        "This execution was already started. It will not be repeated automatically."
    ),
    "revoked": "The device was revoked. The action is no longer authorized.",
}


async def owned_device(db, owner, device_id):
    device = await db.scalar(select(Device).where(Device.id == device_id, Device.user_id == owner))
    if device is None:
        raise AppError("not_found", "Device not found.", 404)
    return device


def device_view(device):
    return {
        "id": device.id,
        "name": device.name,
        "platform": device.platform,
        "created_at": device.created_at,
        "last_seen": device.last_seen,
        "status": "revoked"
        if device.revoked
        else ("online" if device.last_seen >= now() - 15 else "offline"),
    }


def action_view(action):
    return {
        "id": action.id,
        "device_id": action.device_id,
        "tool": action.tool,
        "arguments": json.loads(action.arguments),
        "permission": action.permission,
        "status": action.status,
        "created_at": action.created_at,
        "expires_at": action.expires_at,
        "result": action.result_text,
        "conversation_id": action.conversation_id,
    }


async def sync_action_message(db, action):
    from app.orchestrator import Orchestrator

    text = Orchestrator.action_reply(action.status, action.result_text)
    if action.conversation_id:
        await db.execute(
            update(ChatTurn)
            .where(
                ChatTurn.conversation_id == action.conversation_id,
                ChatTurn.request_id == action.request_id,
            )
            .values(assistant_text=text)
        )


async def expire_actions(db, owner):
    actions = list(
        (
            await db.scalars(
                select(Action)
                .where(
                    Action.user_id == owner,
                    Action.status.in_(["pending_confirmation", "queued", "running"]),
                    Action.expires_at <= now(),
                )
                .limit(100)
            )
        ).all()
    )
    for action in actions:
        text = (
            RESULTS["timeout"]
            if action.status == "running"
            else ("This action expired before dispatch. No action was executed.")
        )
        result = await db.execute(
            update(Action)
            .where(
                Action.id == action.id, Action.status == action.status, Action.expires_at <= now()
            )
            .values(status="expired", result_code="timeout", result_text=text)
        )
        if result.rowcount:
            await db.refresh(action)
            await sync_action_message(db, action)
    await db.commit()


async def create_action(
    db, owner, session_hash, device_id, tool_name, arguments, request_id, conversation_id=None
):
    tool, args = validate_tool(tool_name, arguments)
    device = await owned_device(db, owner, device_id)
    # Serialize creation against revocation and duplicate submissions on this device.
    live = await db.execute(
        update(Device)
        .where(Device.id == device_id, Device.user_id == owner, Device.revoked.is_(False))
        .values(last_seen=Device.last_seen)
    )
    if not live.rowcount:
        raise AppError("device_revoked", "This device has been revoked.", 409)
    if device.last_seen < now() - 15:
        raise AppError(
            "device_offline", "Your selected device is offline. Start Companion and try again.", 409
        )
    existing = await db.scalar(
        select(Action).where(Action.user_id == owner, Action.request_id == request_id)
    )
    if existing:
        if (
            existing.tool != tool_name
            or existing.device_id != device_id
            or existing.conversation_id != conversation_id
            or json.loads(existing.arguments) != args
        ):
            raise AppError(
                "request_conflict", "This request ID has already been used for another action.", 409
            )
        return existing
    action = Action(
        user_id=owner,
        session_hash=session_hash,
        device_id=device_id,
        tool=tool.name,
        arguments=json.dumps(args),
        permission=tool.permission,
        status="pending_confirmation" if tool.permission == "CONFIRM" else "queued",
        expires_at=now() + (120 if tool.permission == "CONFIRM" else 30),
        request_id=request_id,
        conversation_id=conversation_id,
    )
    db.add(action)
    await db.flush()
    return action
