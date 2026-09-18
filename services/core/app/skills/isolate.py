"""6.4: isolate the disputed credit and its supporting evidence at a business-time cutoff."""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import HTTPException
from sqlalchemy import text

from ..clock import sim_now
from ..ledger.mutations import business_day
from ..schemas.api.skills import (
    BillEvidence,
    DeviceEvidence,
    IsolateRequest,
    IsolateResponse,
    IsolationCandidate,
)


def _effective_as_of(connection, as_of: datetime) -> datetime:
    now = sim_now(connection)
    return min(as_of, now)


def _credit_row_to_candidate(row) -> IsolationCandidate:
    return IsolationCandidate(
        txn_id=row["txn_id"],
        utr=row["utr"],
        amount=int(row["amount"]),
        ts=row["ts"],
        counterparty_name=row["counterparty_name"],
    )


def _amount_date_match(row, disputed_amount: int, disputed_date, window_days: int) -> bool:
    if int(row["amount"]) != disputed_amount:
        return False
    payment_date = business_day(row["ts"])
    start = disputed_date - timedelta(days=window_days)
    end = disputed_date + timedelta(days=window_days)
    return start <= payment_date <= end


def _visible_credits(connection, merchant_id: str, as_of: datetime, *, amount: int | None = None):
    filters = "merchant_id = :merchant AND ts <= :as_of"
    values = {"merchant": merchant_id, "as_of": as_of}
    if amount is not None:
        filters += " AND amount = :amount"
        values["amount"] = amount
    return connection.execute(
        text(f"SELECT * FROM rails.credits WHERE {filters} ORDER BY ts, txn_id"),
        values,
    ).mappings().all()


def _select_match(utr_rows, amount_date_rows, disputed_amount, disputed_date, window_days):
    found_by: list[str] = []
    matched = None
    if len(utr_rows) == 1:
        matched = utr_rows[0]
        found_by.append("utr")
        if _amount_date_match(matched, disputed_amount, disputed_date, window_days):
            found_by.append("amount_date")
    elif len(amount_date_rows) == 1 and len(utr_rows) != 1:
        matched = amount_date_rows[0]
        found_by.append("amount_date")
    return matched, found_by


def _seven_day_window(as_of: datetime) -> tuple[datetime, datetime]:
    return as_of - timedelta(days=7), as_of


def _bill_for_credit(connection, merchant_id: str, txn_id: str, as_of: datetime):
    credit = connection.execute(
        text("SELECT amount, pos_bill_id FROM rails.credits WHERE merchant_id = :merchant AND txn_id = :txn AND ts <= :as_of"),
        {"merchant": merchant_id, "txn": txn_id, "as_of": as_of},
    ).mappings().one_or_none()
    if credit is None or not credit["pos_bill_id"]:
        return None
    bill = connection.execute(
        text("""SELECT b.pos_bill_id, b.sim_at, (e.payload->>'total')::bigint AS ledger_total
                FROM rails.bills b
                JOIN ledger.entries e ON e.merchant_id = b.merchant_id AND e.txn_id = b.txn_id
                  AND e.kind = 'bill.linked' AND e.payload->>'bill_id' = b.pos_bill_id
                WHERE b.merchant_id = :merchant AND b.txn_id = :txn AND b.pos_bill_id = :bill_id
                  AND b.sim_at <= :as_of AND e.sim_at <= :as_of
                ORDER BY b.sim_at, b.pos_bill_id LIMIT 1"""),
        {"merchant": merchant_id, "txn": txn_id, "bill_id": credit["pos_bill_id"], "as_of": as_of},
    ).mappings().one_or_none()
    if bill is None:
        return None
    lines = connection.execute(
        text("""SELECT item, line_no, line_amount FROM rails.bill_lines
                WHERE pos_bill_id = :bill AND merchant_id = :merchant AND txn_id = :txn
                ORDER BY line_no"""),
        {"bill": bill["pos_bill_id"], "merchant": merchant_id, "txn": txn_id},
    ).mappings().all()
    if not lines:
        return None
    total = sum(int(line["line_amount"]) for line in lines)
    if total != int(credit["amount"]) or total != bill["ledger_total"]:
        return None
    return BillEvidence(
        bill_id=bill["pos_bill_id"],
        line_items=[line["item"] for line in lines],
        total=int(credit["amount"]),
    )


def _device_for_credit(connection, merchant_id: str, terminal_id: str | None, as_of: datetime):
    if not terminal_id:
        return None
    row = connection.execute(
        text("""SELECT terminal_id, installed_at, data FROM rails.terminals
                WHERE merchant_id = :merchant AND terminal_id = :terminal AND installed_at <= :as_of"""),
        {"merchant": merchant_id, "terminal": terminal_id, "as_of": as_of},
    ).mappings().one_or_none()
    if row is None:
        return None
    data = row["data"] or {}
    device_id = data.get("device_id")
    geo = data.get("geo")
    if not device_id or not isinstance(geo, dict) or "lat" not in geo or "lon" not in geo:
        return None
    return DeviceEvidence(terminal_id=row["terminal_id"], device_id=str(device_id), geo=geo)


def isolate(connection, body: IsolateRequest) -> IsolateResponse:
    as_of = _effective_as_of(connection, body.as_of)
    case = connection.execute(
        text("""SELECT * FROM ops.cases WHERE case_id = :case AND merchant_id = :merchant
                AND opened_at <= :as_of"""),
        {"case": body.case_id, "merchant": body.merchant_id, "as_of": as_of},
    ).mappings().one_or_none()
    if case is None:
        raise HTTPException(404, f"No case {body.case_id} for this merchant at that time.")

    utr_rows = []
    if body.disputed_utr:
        utr_rows = connection.execute(
            text("""SELECT * FROM rails.credits WHERE merchant_id = :merchant AND utr = :utr AND ts <= :as_of
                    ORDER BY ts, txn_id"""),
            {"merchant": body.merchant_id, "utr": body.disputed_utr, "as_of": as_of},
        ).mappings().all()

    amount_date_rows = [
        row
        for row in _visible_credits(connection, body.merchant_id, as_of, amount=body.disputed_amount)
        if _amount_date_match(row, body.disputed_amount, body.disputed_date, body.date_window_days)
    ]

    matched_row, found_by = _select_match(
        utr_rows, amount_date_rows, body.disputed_amount, body.disputed_date, body.date_window_days,
    )

    window_start, window_end = _seven_day_window(as_of)
    same_amount_candidates: list[IsolationCandidate] = []
    for row in _visible_credits(connection, body.merchant_id, as_of, amount=body.disputed_amount):
        if matched_row is not None and row["txn_id"] == matched_row["txn_id"]:
            continue
        if window_start <= row["ts"] <= window_end:
            same_amount_candidates.append(_credit_row_to_candidate(row))
    same_amount_candidates.sort(key=lambda candidate: (candidate.ts, candidate.txn_id))

    seven_day_count = connection.execute(
        text("""SELECT COUNT(*) FROM rails.credits
                WHERE merchant_id = :merchant AND ts <= :as_of AND ts >= :start AND ts <= :end"""),
        {"merchant": body.merchant_id, "as_of": as_of, "start": window_start, "end": window_end},
    ).scalar_one()

    matched = _credit_row_to_candidate(matched_row) if matched_row else None
    bill = _bill_for_credit(connection, body.merchant_id, matched_row["txn_id"], as_of) if matched_row else None
    device = (
        _device_for_credit(connection, body.merchant_id, matched_row.get("terminal_id"), as_of)
        if matched_row
        else None
    )

    return IsolateResponse(
        matched=matched,
        found_by=found_by,
        same_amount_candidates=same_amount_candidates,
        bill=bill,
        device=device,
        seven_day_credit_count=seven_day_count,
    )
