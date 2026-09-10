import hashlib
import secrets
import uuid
from typing import Annotated

from fastapi import Depends, Request
from fastapi_users import BaseUserManager, FastAPIUsers, UUIDIDMixin, schemas
from fastapi_users.authentication import AuthenticationBackend, CookieTransport
from fastapi_users.authentication.strategy.db import DatabaseStrategy
from fastapi_users.db import SQLAlchemyUserDatabase
from fastapi_users.exceptions import InvalidPasswordException
from fastapi_users_db_sqlalchemy.access_token import SQLAlchemyAccessTokenDatabase
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionToken, User, get_db
from app.errors import AppError

COOKIE_NAME = "thryv_session"


def digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


class UserRead(schemas.BaseUser[uuid.UUID]):
    pass


class UserCreate(schemas.BaseUserCreate):
    password: str = Field(min_length=12, max_length=128)


class UserManager(UUIDIDMixin, BaseUserManager[User, uuid.UUID]):
    async def validate_password(self, password, user):
        if not 12 <= len(password) <= 128:
            raise InvalidPasswordException(reason="Use a password between 12 and 128 characters.")


async def get_user_manager(db: Annotated[AsyncSession, Depends(get_db)]):
    yield UserManager(SQLAlchemyUserDatabase(db, User))


class HashedDatabaseStrategy(DatabaseStrategy):
    """Retain the library's session lifecycle; store only a token digest."""

    async def write_token(self, user):
        raw = secrets.token_urlsafe(32)
        await self.database.create({"token": digest(raw), "user_id": user.id})
        return raw

    async def read_token(self, token, user_manager):
        return await super().read_token(digest(token) if token else None, user_manager)

    async def destroy_token(self, token, user):
        await super().destroy_token(digest(token), user)


async def get_strategy(request: Request, db: Annotated[AsyncSession, Depends(get_db)]):
    return HashedDatabaseStrategy(
        SQLAlchemyAccessTokenDatabase(db, SessionToken),
        lifetime_seconds=request.app.state.settings.session_lifetime_seconds,
    )


async def current_user(
    request: Request,
    strategy: Annotated[HashedDatabaseStrategy, Depends(get_strategy)],
    manager: Annotated[UserManager, Depends(get_user_manager)],
) -> User:
    user = await strategy.read_token(request.cookies.get(COOKIE_NAME), manager)
    if user is None or not user.is_active:
        raise AppError("unauthenticated", "Sign in to your THRYV account to continue.", 401)
    return user


Account = Annotated[User, Depends(current_user)]
DB = Annotated[AsyncSession, Depends(get_db)]


def install_auth(app, settings):
    transport = CookieTransport(
        cookie_name=COOKIE_NAME,
        cookie_max_age=settings.session_lifetime_seconds,
        cookie_secure=settings.app_env == "production",
        cookie_httponly=True,
        cookie_samesite="lax",
    )
    backend = AuthenticationBackend(name="session", transport=transport, get_strategy=get_strategy)
    users = FastAPIUsers[User, uuid.UUID](get_user_manager, [backend])
    app.include_router(users.get_register_router(UserRead, UserCreate), prefix="/api/auth")
    app.include_router(users.get_auth_router(backend), prefix="/api/auth")
