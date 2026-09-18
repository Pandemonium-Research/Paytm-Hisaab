"""Postgres connections. Application code never loads the migration owner's URL."""

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Connection, Engine, create_engine

from .config import get_settings


def sqlalchemy_url(url: str) -> str:
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@lru_cache(maxsize=4)
def engine_for_url(url: str) -> Engine:
    return create_engine(sqlalchemy_url(url), pool_pre_ping=True)


@contextmanager
def transaction() -> Iterator[Connection]:
    with engine_for_url(get_settings().database_url).begin() as connection:
        yield connection
