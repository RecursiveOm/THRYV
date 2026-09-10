import asyncio
import os

from alembic import context
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import Settings
from app.database import Base

config = context.config
url = config.attributes.get("database_url") or Settings().database_url.get_secret_value()


def run(connection):
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def online():
    engine = create_async_engine(url, hide_parameters=True)
    async with engine.connect() as connection:
        await connection.run_sync(run)
    await engine.dispose()


if context.is_offline_mode():
    context.configure(url=url, target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    previous_umask = os.umask(0o077)
    try:
        asyncio.run(online())
    finally:
        os.umask(previous_umask)
