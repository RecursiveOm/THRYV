import time
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from fastapi import Request
from fastapi_users.db import SQLAlchemyBaseUserTableUUID
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyBaseAccessTokenTableUUID
from fastapi_users_db_sqlalchemy.generics import GUID
from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text, UniqueConstraint, event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now() -> int:
    return int(datetime.now(UTC).timestamp())


def conversation_clock() -> int:
    return time.time_ns() // 1_000_000


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class User(SQLAlchemyBaseUserTableUUID, Base):
    pass


class SessionToken(SQLAlchemyBaseAccessTokenTableUUID, Base):
    token: Mapped[str] = mapped_column(String(64), primary_key=True)


class ProviderCredential(Base):
    __tablename__ = "provider_credential"
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    ciphertext: Mapped[str] = mapped_column(Text)


class Conversation(Base):
    __tablename__ = "conversation"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(120), default="New conversation")
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    updated_at: Mapped[int] = mapped_column(BigInteger, default=conversation_clock, index=True)
    busy_until: Mapped[int] = mapped_column(Integer, default=0)
    browser_state: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")


class ChatTurn(Base):
    __tablename__ = "chat_turn"
    __table_args__ = (UniqueConstraint("conversation_id", "request_id"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversation.id", ondelete="CASCADE"), index=True
    )
    request_id: Mapped[str] = mapped_column(String(36))
    user_text: Mapped[str] = mapped_column(Text)
    assistant_text: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(24), default="running")
    created_at: Mapped[int] = mapped_column(Integer, default=now, index=True)


class Device(Base):
    __tablename__ = "device"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(80))
    platform: Mapped[str] = mapped_column(String(30))
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    last_seen: Mapped[int] = mapped_column(Integer, default=0)
    revoked: Mapped[bool] = mapped_column(default=False)


class Pairing(Base):
    __tablename__ = "pairing"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    expires_at: Mapped[int] = mapped_column(Integer)
    used: Mapped[bool] = mapped_column(default=False)


class Action(Base):
    __tablename__ = "action"
    __table_args__ = (UniqueConstraint("user_id", "request_id"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    device_id: Mapped[str | None] = mapped_column(
        ForeignKey("device.id"), index=True, nullable=True
    )
    conversation_id: Mapped[str | None] = mapped_column(
        ForeignKey("conversation.id", ondelete="SET NULL"), nullable=True
    )
    request_id: Mapped[str] = mapped_column(String(36))
    session_hash: Mapped[str] = mapped_column(String(64))
    tool: Mapped[str] = mapped_column(String(60))
    arguments: Mapped[str] = mapped_column(Text)
    permission: Mapped[str] = mapped_column(String(12))
    status: Mapped[str] = mapped_column(String(24), index=True)
    created_at: Mapped[int] = mapped_column(Integer, default=now)
    expires_at: Mapped[int] = mapped_column(Integer)
    result_code: Mapped[str | None] = mapped_column(String(40), nullable=True)
    result_text: Mapped[str | None] = mapped_column(String(500), nullable=True)
    details: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")


def configure_database(app, url: str):
    engine = create_async_engine(url, echo=False, hide_parameters=True)
    if url.startswith("sqlite"):

        @event.listens_for(engine.sync_engine, "connect")
        def sqlite_options(connection, _):
            cursor = connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    app.state.engine = engine
    app.state.sessions = async_sessionmaker(engine, expire_on_commit=False)


async def get_db(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.sessions() as session:
        yield session


class MemorySetting(Base):
    __tablename__ = "memory_setting"
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(default=True)


class PersonalMemory(Base):
    __tablename__ = "personal_memory"
    __table_args__ = (UniqueConstraint("user_id", "content_hash"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("user.id", ondelete="CASCADE"), index=True
    )
    category: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(String(500))
    content_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[int] = mapped_column(Integer, default=now)


class VoiceSetting(Base):
    __tablename__ = "voice_setting"
    user_id: Mapped[uuid.UUID] = mapped_column(
        GUID, ForeignKey("user.id", ondelete="CASCADE"), primary_key=True
    )
    wake_enabled: Mapped[bool] = mapped_column(default=False)
