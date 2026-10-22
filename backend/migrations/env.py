from alembic import context

from models import *  # noqa: F401,F403 - register all model metadata
from services.database import db


config = context.config
target_metadata = db.metadata


def run_migrations_offline():
    raise RuntimeError("Offline migrations are not supported by the application startup runner")


def run_migrations_online():
    connection = config.attributes.get("connection")
    if connection is None:
        raise RuntimeError("Migrations must be run through services.database.init_db")
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
