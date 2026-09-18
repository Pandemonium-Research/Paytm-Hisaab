"""Payment reads derived from stored rails and append-only evidence."""

import base64
import binascii
import json
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import text

from ..schemas.api.reads import CreditRead, MerchantResponse


def merchant(connection, merchant_id):
    profile = connection.execute(text("SELECT profile FROM rails.merchants WHERE merchant_id = :merchant"), {"merchant": merchant_id}).scalar_one_or_none()
    if profile is None:
        raise HTTPException(404, f"Merchant {merchant_id} was not loaded; replay a generated split first.")
    saved = connection.execute(text("SELECT data FROM ops.settings WHERE key = :key"), {"key": f"profile:{merchant_id}"}).scalar_one_or_none()
    if saved:
        profile["preferred_language"] = saved["language"]
    return MerchantResponse.model_validate(profile)


def credit(connection, txn_id, as_of, merchant_id=None):
    row = connection.execute(text("SELECT * FROM rails.credits WHERE txn_id = :txn AND ts <= :as_of"), {"txn": txn_id, "as_of": as_of}).mappings().one_or_none()
    if row is None or merchant_id is not None and row["merchant_id"] != merchant_id:
        raise HTTPException(404, f"Payment {txn_id} was not found at this time for this merchant.")
    return dict(row)


def as_credit_read(row):
    transaction = {key: value for key, value in row.items() if key not in {"machine_label", "claim_label", "effective_label", "tier", "conflict", "entry_refs"}}
    transaction["direction"] = "CR"
    return CreditRead.model_validate({"transaction": transaction, **{
        key: row.get(key) for key in ("machine_label", "claim_label", "effective_label", "tier", "conflict", "entry_refs")
    }})


def read_credit(connection, txn_id, as_of):
    value = credit(connection, txn_id, as_of)
    projection = connection.execute(text("SELECT * FROM ledger.current_view(:merchant, :as_of) WHERE txn_id = :txn"),
        {"merchant": value["merchant_id"], "as_of": as_of, "txn": txn_id}).mappings().one()
    return as_credit_read({**value, **dict(projection)})


def cursor_encode(timestamp, txn_id):
    return base64.urlsafe_b64encode(json.dumps([timestamp.isoformat(), txn_id]).encode()).decode()


def cursor_decode(value):
    try:
        timestamp, txn_id = json.loads(base64.urlsafe_b64decode(value.encode()).decode())
        parsed = datetime.fromisoformat(timestamp)
        if not isinstance(txn_id, str) or parsed.tzinfo is None:
            raise ValueError()
        return parsed, txn_id
    except (ValueError, TypeError, UnicodeError, KeyError, binascii.Error) as exc:
        raise HTTPException(422, "Use the next_cursor returned by this endpoint.") from exc


def read_credits(connection, merchant_id, as_of, limit, cursor=None, *, descending=False):
    merchant(connection, merchant_id)
    filters, values = "", {"merchant": merchant_id, "as_of": as_of, "limit": limit + 1}
    if cursor:
        values["cursor_ts"], values["cursor_txn"] = cursor_decode(cursor)
        operator = "<" if descending else ">"
        filters = f"AND (c.ts, c.txn_id) {operator} (:cursor_ts, :cursor_txn)"
    direction = "DESC" if descending else "ASC"
    rows = connection.execute(text(f"""SELECT c.*, v.machine_label, v.claim_label, v.effective_label,
        v.conflict, v.entry_refs, v.tier FROM rails.credits c
        JOIN ledger.current_view(:merchant, :as_of) v USING (txn_id)
        WHERE c.merchant_id = :merchant AND c.ts <= :as_of {filters}
        ORDER BY c.ts {direction}, c.txn_id {direction} LIMIT :limit"""), values).mappings().all()
    page = rows[:limit]
    next_cursor = cursor_encode(page[-1]["ts"], page[-1]["txn_id"]) if len(rows) > limit else None
    return [as_credit_read(dict(row)) for row in page], next_cursor
