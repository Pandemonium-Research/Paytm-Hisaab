"""Persistent business clock, independent of the database's evidence timestamps."""

import json
from datetime import datetime

from sqlalchemy import text


INITIAL_TIME = datetime.fromisoformat("2025-04-01T00:00:00+05:30")


def sim_now(connection):
    value = connection.execute(text("SELECT data FROM ops.settings WHERE key = 'sim_clock'")).scalar_one_or_none()
    return datetime.fromisoformat(value["sim_at"]) if value else INITIAL_TIME


def set_clock(connection, value):
    connection.execute(
        text("""INSERT INTO ops.settings (key, data) VALUES ('sim_clock', CAST(:data AS jsonb))
                ON CONFLICT (key) DO UPDATE SET data = excluded.data"""),
        {"data": json.dumps({"sim_at": value.isoformat()})},
    )
    return value
