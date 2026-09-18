"""Migrations connect as the owner, independently of the running application's settings."""

import os

from alembic import context
from sqlalchemy import create_engine, pool

from app.db import sqlalchemy_url


url = sqlalchemy_url(os.environ["DATABASE_OWNER_URL"])

if context.is_offline_mode():
    context.configure(url=url, literal_binds=True, version_table_schema="ops")
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, version_table_schema="ops")
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()
