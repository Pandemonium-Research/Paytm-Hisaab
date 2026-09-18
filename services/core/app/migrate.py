"""Idempotent role bootstrap, followed by Alembic as the schema owner.

Only the compose migration service has the bootstrap and owner credentials. Works on existing
volumes as well as fresh clones; changing a db entrypoint file alone would skip existing volumes.
"""

import argparse
import os
from pathlib import Path

import psycopg
from alembic import command
from alembic.config import Config
from psycopg import sql
from sqlalchemy.engine import make_url


def bootstrap(url: str) -> None:
    with psycopg.connect(url) as connection:
        for role, password_variable in (
            ("hisaab_owner", "HISAAB_DB_OWNER_PASSWORD"),
            ("hisaab_app", "HISAAB_DB_APP_PASSWORD"),
        ):
            if not connection.execute(
                "SELECT 1 FROM pg_roles WHERE rolname = %s", (role,)
            ).fetchone():
                connection.execute(sql.SQL("CREATE ROLE {}").format(sql.Identifier(role)))
            connection.execute(
                sql.SQL(
                    "ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                    "NOREPLICATION NOBYPASSRLS PASSWORD {}"
                ).format(sql.Identifier(role), sql.Literal(os.environ[password_variable]))
            )
        connection.execute("REVOKE CREATE ON SCHEMA public FROM PUBLIC")
        for schema in ("rails", "ledger", "ops"):
            connection.execute(
                sql.SQL("CREATE SCHEMA IF NOT EXISTS {} AUTHORIZATION hisaab_owner").format(
                    sql.Identifier(schema)
                )
            )
        database = connection.execute("SELECT current_database()").fetchone()[0]
        connection.execute(
            sql.SQL("GRANT CONNECT ON DATABASE {} TO hisaab_owner, hisaab_app").format(
                sql.Identifier(database)
            )
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test-database", action="store_true")
    args = parser.parse_args()
    url = os.environ["HISAAB_BOOTSTRAP_DATABASE_URL"]
    if args.test_database:
        with psycopg.connect(url, autocommit=True) as connection:
            if not connection.execute(
                "SELECT 1 FROM pg_database WHERE datname = 'hisaab_ledger_test'"
            ).fetchone():
                connection.execute("CREATE DATABASE hisaab_ledger_test")
        url = make_url(url).set(database="hisaab_ledger_test").render_as_string(hide_password=False)
        os.environ["DATABASE_OWNER_URL"] = make_url(os.environ["DATABASE_OWNER_URL"]).set(
            database="hisaab_ledger_test"
        ).render_as_string(hide_password=False)
    bootstrap(url)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, "head")


if __name__ == "__main__":
    main()
