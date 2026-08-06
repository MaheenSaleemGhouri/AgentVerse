"""Alembic environment — async, reads DATABASE_URL from Settings
(never a second hardcoded connection string; CLAUDE.md §7)."""

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

from agentverse_api.auth_service.infrastructure import models as auth_models  # noqa: F401
from agentverse_api.billing_service.infrastructure import models as billing_models  # noqa: F401
from agentverse_api.infrastructure.config import get_settings
from agentverse_api.infrastructure.orm_base import Base
from agentverse_api.marketplace_service.infrastructure import (  # noqa: F401
    models as marketplace_models,
)
from agentverse_api.notification_service.infrastructure import (  # noqa: F401
    models as notification_models,
)
from agentverse_api.orchestration_service.infrastructure import (  # noqa: F401
    models as orchestration_models,
)

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# All bounded-context ORM models must be imported above so Base.metadata
# is fully populated before autogenerate diffs against it.
target_metadata = Base.metadata


def get_url() -> str:
    return get_settings().database_url


def run_migrations_offline() -> None:
    context.configure(
        url=get_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()
    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
