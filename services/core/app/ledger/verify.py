"""Verify raw stored rows and the persisted head from one database snapshot."""

from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import Connection, text

from ..schemas.api.ledger_ops import LedgerVerifyResponse
from .chain import GENESIS_HASH, entry_hash


def broken_index(rows: Sequence[Mapping[str, Any]]) -> int | None:
    previous = GENESIS_HASH
    for expected, row in enumerate(rows):
        if row["chain_index"] != expected:
            return expected
        try:
            digest = entry_hash(row, previous)
        except (ValueError, TypeError, KeyError):
            return expected
        if bytes(row["prev_hash"]) != previous or bytes(row["hash"]) != digest:
            return expected
        previous = bytes(row["hash"])
    return None


def verify(connection: Connection, merchant_id: str) -> LedgerVerifyResponse:
    # A single SELECT shares one MVCC snapshot even at READ COMMITTED, so a concurrent append
    # cannot make entries and their head disagree between two separate queries.
    result = connection.execute(
        text("""SELECT e.*, h.chain_index AS head_index, h.hash AS head_hash
                FROM ledger.chain_heads h FULL OUTER JOIN ledger.entries e USING (merchant_id)
                WHERE coalesce(h.merchant_id, e.merchant_id) = :merchant ORDER BY e.chain_index"""),
        {"merchant": merchant_id},
    ).mappings().all()
    rows = [row for row in result if row["seq"] is not None]
    broken = broken_index(rows)
    if broken is None and result:
        expected_index = len(rows) - 1
        expected_hash = bytes(rows[-1]["hash"]) if rows else GENESIS_HASH
        if result[0]["head_index"] is None:
            broken = 0
        elif result[0]["head_index"] != expected_index or bytes(result[0]["head_hash"]) != expected_hash:
            broken = len(rows)
    return LedgerVerifyResponse(merchant_id=merchant_id, ok=broken is None, broken_at=broken)
