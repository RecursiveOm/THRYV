import uuid

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update

from app.auth import DB, Account
from app.database import Action, Device, Workspace
from app.device_api import Companion
from app.errors import AppError

router = APIRouter()


class Grant(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: uuid.UUID
    name: str = Field(min_length=1, max_length=80)
    path: str = Field(min_length=1, max_length=1000, pattern=r"^/")


class Grants(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspaces: list[Grant] = Field(max_length=20)


async def owned_workspace(db, owner, identifier, device_id=None):
    item = await db.scalar(
        select(Workspace)
        .join(Device)
        .where(
            Workspace.id == identifier,
            Workspace.user_id == owner,
            Workspace.revoked.is_(False),
            Device.revoked.is_(False),
        )
    )
    if item is None or (device_id is not None and item.device_id != device_id):
        raise AppError(
            "workspace_unavailable", "Select an authorized workspace on this device.", 403
        )
    return item


@router.post("/api/companion/workspaces")
async def sync(body: Grants, device: Companion, db: DB):
    ids = [str(g.id) for g in body.workspaces]
    current = (await db.scalars(select(Workspace).where(Workspace.device_id == device.id))).all()
    for grant in body.workspaces:
        item = await db.get(Workspace, str(grant.id))
        if item and (item.user_id != device.user_id or item.device_id != device.id):
            raise AppError(
                "workspace_conflict", "Workspace identifier belongs to another device.", 409
            )
        if item:
            if item.path != grant.path:
                raise AppError("workspace_conflict", "Authorize the moved workspace again.", 409)
        else:
            db.add(
                Workspace(
                    id=str(grant.id),
                    user_id=device.user_id,
                    device_id=device.id,
                    name=grant.name,
                    path=grant.path,
                    active=False,
                    revoked=False,
                )
            )
    for item in current:
        if item.id not in ids:
            item.revoked, item.active = True, False
    await db.commit()
    return {"revoked": [item.id for item in current if item.revoked]}


@router.get("/api/workspaces")
async def workspaces(user: Account, db: DB):
    items = (
        await db.scalars(
            select(Workspace)
            .join(Device)
            .where(
                Workspace.user_id == user.id,
                Workspace.revoked.is_(False),
                Device.revoked.is_(False),
            )
            .limit(100)
        )
    ).all()
    return [
        {"id": i.id, "device_id": i.device_id, "name": i.name, "path": i.path, "active": i.active}
        for i in items
    ]


@router.post("/api/workspaces/{identifier}/select")
async def select_workspace(identifier: uuid.UUID, user: Account, db: DB):
    item = await owned_workspace(db, user.id, str(identifier))
    await db.execute(update(Workspace).where(Workspace.user_id == user.id).values(active=False))
    item.active = True
    await db.commit()
    return {"selected": item.id, "device_id": item.device_id}


@router.delete("/api/workspaces/{identifier}")
async def revoke(identifier: uuid.UUID, user: Account, db: DB):
    item = await owned_workspace(db, user.id, str(identifier))
    item.revoked, item.active = True, False
    # Revoke queued/running workspace actions before the next independent authorization check.
    actions = (
        await db.scalars(
            select(Action).where(
                Action.user_id == user.id,
                Action.device_id == item.device_id,
                Action.status.in_(["pending_confirmation", "queued", "running"]),
            )
        )
    ).all()
    import json

    for action in actions:
        if json.loads(action.arguments).get("workspace_id") == item.id:
            action.status, action.result_code = "cancelled", "revoked"
            action.result_text = "Workspace authorization was revoked."
    await db.commit()
    return {"revoked": True}
