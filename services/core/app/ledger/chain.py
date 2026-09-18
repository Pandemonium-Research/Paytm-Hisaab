"""Canonical SHA-256 chain, serialized independently for each merchant."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, TypeAdapter
from sqlalchemy import Connection, text

from ..auth import check_entry_kind
from ..schemas.api.ledger_ops import AGENT_CONFIDENCE_CAP
from ..schemas.ledger import EntryKind, LedgerEntry, LedgerEntryVariant, PAYLOAD_MODELS
from ..schemas.roles import Role


GENESIS_HASH = bytes(32)
HASH_FIELDS = (
    "merchant_id", "chain_index", "kind", "txn_id", "payload", "actor_role", "sim_at", "recorded_at",
)
ENTRY_ADAPTER = TypeAdapter(LedgerEntryVariant)


def lock_head(connection, merchant_id):
    connection.execute(
        text("""INSERT INTO ledger.chain_heads (merchant_id, chain_index, hash)
                VALUES (:merchant, -1, :genesis) ON CONFLICT (merchant_id) DO NOTHING"""),
        {"merchant": merchant_id, "genesis": GENESIS_HASH},
    )
    return connection.execute(
        text("SELECT chain_index, hash FROM ledger.chain_heads WHERE merchant_id = :merchant FOR UPDATE"),
        {"merchant": merchant_id},
    ).mappings().one()


def _normalise(value: Any) -> Any:
    if isinstance(value, Enum):
        return _normalise(value.value)
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("canonical timestamps must be timezone-aware")
        # Postgres changes the representation of timestamptz on read. Hash the instant in UTC.
        return value.astimezone(timezone.utc).isoformat(timespec="microseconds")
    if isinstance(value, BaseModel):
        return _normalise(value.model_dump(mode="python"))
    if isinstance(value, Mapping):
        if any(not isinstance(key, str) for key in value):
            raise TypeError("canonical JSON object keys must be strings")
        return {key: _normalise(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalise(item) for item in value]
    return value


def canonical_json(value: Any) -> bytes:
    return json.dumps(
        _normalise(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")


def entry_hash(entry: Mapping[str, Any], prev_hash: bytes) -> bytes:
    if len(prev_hash) != 32:
        raise ValueError("previous hash must be 32 bytes")
    return hashlib.sha256(canonical_json({key: entry[key] for key in HASH_FIELDS}) + prev_hash).digest()


def append(
    connection: Connection, *, merchant_id: str, kind: EntryKind, payload: BaseModel | Mapping[str, Any],
    actor_role: Role, actor_ref: str, sim_at: datetime, txn_id: str | None = None,
) -> LedgerEntry:
    """Append inside the caller's transaction so ops state and evidence commit together.

    The lock lasts until that transaction commits. recorded_at has no caller argument: select
    Postgres clock_timestamp() after acquiring the head, then use that same instant in the hash
    and row. A Python wall clock cannot backdate evidence.
    """
    if not connection.in_transaction():
        raise RuntimeError("ledger append requires an explicit transaction")
    kind, actor_role = EntryKind(kind), Role(actor_role)
    check_entry_kind(actor_role, kind)
    payload_model = PAYLOAD_MODELS[kind].model_validate(
        payload.model_dump(mode="python") if isinstance(payload, BaseModel) else payload
    )
    if (
        kind is EntryKind.LABEL_PROPOSED
        and payload_model.source.value == "agent"
        and payload_model.confidence > AGENT_CONFIDENCE_CAP
    ):
        raise ValueError(f"agent confidence must be at most {AGENT_CONFIDENCE_CAP}")
    if not merchant_id or not actor_ref:
        raise ValueError("merchant_id and actor_ref must be nonempty")
    _normalise(sim_at)
    # Round-trip through JSONB before hashing: JSON numbers such as 1.0 can become 1 in Postgres.
    # Timestamp strings inside payloads stay strings; only envelope times are timestamptz columns.
    stored_payload = connection.execute(
        text("SELECT CAST(:payload AS jsonb)"), {"payload": payload_model.model_dump_json()},
    ).scalar_one()
    head = lock_head(connection, merchant_id)
    row = {
        "merchant_id": merchant_id, "chain_index": head["chain_index"] + 1,
        "kind": kind.value, "txn_id": txn_id, "payload": stored_payload,
        "actor_role": actor_role.value, "actor_ref": actor_ref, "sim_at": sim_at,
        "recorded_at": connection.execute(text("SELECT clock_timestamp()")).scalar_one(),
        "prev_hash": bytes(head["hash"]),
    }
    row["hash"] = entry_hash(row, row["prev_hash"])
    # Validate the complete wire envelope before the INSERT (including an aware sim_at).
    ENTRY_ADAPTER.validate_python({"seq": 1, **row})
    stored = connection.execute(
        text("""INSERT INTO ledger.entries
                (merchant_id, chain_index, kind, txn_id, payload, actor_role, actor_ref,
                 sim_at, recorded_at, prev_hash, hash)
                VALUES (:merchant_id, :chain_index, :kind, :txn_id, CAST(:payload AS jsonb),
                        :actor_role, :actor_ref, :sim_at, :recorded_at, :prev_hash, :hash)
                RETURNING *"""),
        {**row, "payload": canonical_json(stored_payload).decode("utf-8")},
    ).mappings().one()
    connection.execute(
        text("UPDATE ledger.chain_heads SET chain_index = :chain_index, hash = :hash WHERE merchant_id = :merchant_id"),
        {key: row[key] for key in ("chain_index", "hash", "merchant_id")},
    )
    return LedgerEntry.model_validate(dict(stored))
