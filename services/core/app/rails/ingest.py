"""Idempotent source ingestion, with evidence committed in the same transaction."""

import json
from collections import defaultdict

from fastapi import HTTPException
from sqlalchemy import text

from ..ledger.chain import append
from ..schemas.ledger import EntryKind
from ..schemas.roles import Role
from . import freeze


def ingest_transactions(connection, transactions, sim_at, *, debit=False):
    table = "debits" if debit else "credits"
    accepted, duplicates = 0, []
    for transaction in transactions:
        if transaction.ts > sim_at:
            raise HTTPException(422, "A payment cannot be observed before its timestamp.")
        values = transaction.model_dump(mode="python", exclude={"direction"})
        values["channel"] = transaction.channel.value
        inserted = connection.execute(
            text(f"""INSERT INTO rails.{table}
                (txn_id, merchant_id, ts, amount, channel, counterparty_id, counterparty_handle,
                 counterparty_name, terminal_id, pos_bill_id, utr, orig_txn_id, note)
                VALUES (:txn_id, :merchant_id, :ts, :amount, :channel, :counterparty_id,
                        :counterparty_handle, :counterparty_name, :terminal_id, :pos_bill_id,
                        :utr, :orig_txn_id, :note) ON CONFLICT (txn_id) DO NOTHING RETURNING txn_id"""),
            values,
        ).scalar_one_or_none()
        if inserted is None:
            existing = connection.execute(text(f"SELECT * FROM rails.{table} WHERE txn_id = :txn"), {"txn": transaction.txn_id}).mappings().one()
            if any(existing[key] != value for key, value in values.items()):
                raise HTTPException(409, f"Payment {transaction.txn_id} already exists with different data.")
            duplicates.append(transaction.txn_id)
            continue
        accepted += 1
        connection.execute(
            text("""INSERT INTO rails.counterparties (merchant_id, counterparty_id, data)
                    VALUES (:merchant, :payer, CAST(:data AS jsonb))
                    ON CONFLICT (merchant_id, counterparty_id) DO NOTHING"""),
            {"merchant": transaction.merchant_id, "payer": transaction.counterparty_id,
             "data": json.dumps({"name": transaction.counterparty_name, "handle": transaction.counterparty_handle})},
        )
        if not debit:
            append(connection, merchant_id=transaction.merchant_id, txn_id=transaction.txn_id,
                   kind=EntryKind.CREDIT_OBSERVED, actor_role=Role.RAILS, actor_ref="rails",
                   sim_at=sim_at, payload={"amount": transaction.amount,
                       "channel": transaction.channel.value, "counterparty_id": transaction.counterparty_id})
    return accepted, duplicates


def ingest_bills(connection, lines, sim_at):
    groups = defaultdict(list)
    for line in lines:
        groups[line.pos_bill_id].append(line)
    accepted, linked = 0, []
    for bill_id, bill_lines in groups.items():
        first = bill_lines[0]
        credit = connection.execute(text("SELECT * FROM rails.credits WHERE txn_id = :txn AND merchant_id = :merchant AND ts <= :as_of"),
            {"txn": first.txn_id, "merchant": first.merchant_id, "as_of": sim_at}).mappings().one_or_none()
        if credit is None:
            raise HTTPException(404, f"Visible payment {first.txn_id} was not found for this bill.")
        if credit["pos_bill_id"] != bill_id or any((line.txn_id, line.merchant_id) != (first.txn_id, first.merchant_id) for line in bill_lines):
            raise HTTPException(422, "Bill lines must belong to the payment's linked bill and merchant.")
        if len({line.line_no for line in bill_lines}) != len(bill_lines) or sum(line.line_amount for line in bill_lines) != credit["amount"]:
            raise HTTPException(422, "Send the complete bill with distinct lines and a total matching the payment.")
        existing = connection.execute(text("SELECT * FROM rails.bill_lines WHERE pos_bill_id = :bill ORDER BY line_no"), {"bill": bill_id}).mappings().all()
        submitted = sorted([line.model_dump() for line in bill_lines], key=lambda line: line["line_no"])
        if existing:
            if [dict(line) for line in existing] != submitted:
                raise HTTPException(409, f"Bill {bill_id} already exists with different lines.")
            continue
        connection.execute(text("INSERT INTO rails.bills (pos_bill_id, merchant_id, txn_id, sim_at) VALUES (:bill, :merchant, :txn, :as_of)"),
            {"bill": bill_id, "merchant": first.merchant_id, "txn": first.txn_id, "as_of": sim_at})
        connection.execute(text("""INSERT INTO rails.bill_lines
            (pos_bill_id, line_no, txn_id, merchant_id, item, hsn, qty, unit, rate, line_amount)
            VALUES (:pos_bill_id, :line_no, :txn_id, :merchant_id, :item, :hsn, :qty, :unit, :rate, :line_amount)"""), submitted)
        append(connection, merchant_id=first.merchant_id, txn_id=first.txn_id,
               kind=EntryKind.BILL_LINKED, actor_role=Role.RAILS, actor_ref="rails", sim_at=sim_at,
               payload={"bill_id": bill_id, "line_count": len(bill_lines), "total": credit["amount"]})
        accepted += len(bill_lines)
        linked.append(bill_id)
    return accepted, linked


def ingest_events(connection, events, sim_at):
    """Ingest events and open a freeze case for any lien among them.

    Returns the accepted count and one WF20 body per case opened. The caller fires those after
    the transaction commits, so the workflow cannot ask core about a case that is not there yet.
    """
    accepted, notifications = 0, []
    # Business-time order: a decline burst is read back from the table, so it has to be stored
    # before the lien it precedes, however the batch happened to be ordered.
    for event in sorted(events, key=lambda item: item.ts):
        if event.ts > sim_at:
            raise HTTPException(422, "An event cannot be observed before its timestamp.")
        data = event.model_dump(mode="json")
        inserted = connection.execute(text("""INSERT INTO rails.events (event_id, merchant_id, ts, type, data)
            VALUES (:event_id, :merchant_id, :ts, :type, CAST(:data AS jsonb))
            ON CONFLICT (event_id) DO NOTHING RETURNING event_id"""),
            {"event_id": event.event_id, "merchant_id": event.merchant_id, "ts": event.ts,
             "type": data["type"], "data": json.dumps(data)}).scalar_one_or_none()
        if inserted is None:
            continue
        accepted += 1
        # After the insert: the burst is counted from the events table, and this lien's own row
        # must be there for a replay of the same batch to behave like the first run.
        opened = freeze.detect(connection, event)
        if opened is not None:
            notifications.append(opened)
    return accepted, notifications
