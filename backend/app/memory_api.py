import uuid
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from sqlalchemy import delete, select, update

from app.auth import DB, Account
from app.database import MemorySetting, PersonalMemory, User
from app.errors import AppError
from app.memory import enabled, save, view

router = APIRouter()


class MemoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    content: str = Field(min_length=3, max_length=500)
    category: Literal["preference", "fact", "project", "decision"] = "fact"


class Toggle(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool


@router.get("/api/memories")
async def memories(user: Account, db: DB):
    items = (
        await db.scalars(
            select(PersonalMemory)
            .where(PersonalMemory.user_id == user.id)
            .order_by(PersonalMemory.created_at.desc())
            .limit(200)
        )
    ).all()
    return {"enabled": await enabled(db, user.id), "memories": [view(item) for item in items]}


@router.post("/api/memories")
async def remember(body: MemoryInput, user: Account, db: DB):
    item = await save(db, user.id, body.content, body.category)
    await db.commit()
    return view(item)


@router.post("/api/memories/settings")
async def settings(body: Toggle, user: Account, db: DB):
    await db.execute(update(User).where(User.id == user.id).values(is_active=User.is_active))
    setting = await db.get(MemorySetting, user.id)
    if setting:
        setting.enabled = body.enabled
    else:
        db.add(MemorySetting(user_id=user.id, enabled=body.enabled))
    await db.commit()
    return {"enabled": body.enabled}


@router.delete("/api/memories/{memory_id}")
async def forget(memory_id: uuid.UUID, user: Account, db: DB):
    result = await db.execute(
        delete(PersonalMemory).where(
            PersonalMemory.id == str(memory_id), PersonalMemory.user_id == user.id
        )
    )
    if not result.rowcount:
        raise AppError("not_found", "Memory not found.", 404)
    await db.commit()
    return {"deleted": True}


@router.delete("/api/memories")
async def clear(user: Account, db: DB):
    await db.execute(delete(PersonalMemory).where(PersonalMemory.user_id == user.id))
    await db.commit()
    return {"cleared": True}
