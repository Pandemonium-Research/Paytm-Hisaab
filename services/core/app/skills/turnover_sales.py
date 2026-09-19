"""Shared period sale loading and per-credit aggregate contributions for turnover skills."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from sqlalchemy import text

from ..clock import sim_now
from ..ledger.mutations import business_day
from ..schemas.common import PredictionLabel

SALE_LABELS = frozenset({PredictionLabel.TAXABLE_SUPPLY.value, PredictionLabel.EXEMPT_SUPPLY.value})


def effective_as_of(connection, as_of: datetime) -> datetime:
    return min(as_of, sim_now(connection))


def _usable_label(label: str | None) -> bool:
    return label is not None and label != PredictionLabel.UNCLASSIFIED.value


def load_period_credit_rows(
    connection,
    merchant_id: str,
    as_of: datetime,
    period_from: date,
    period_to: date,
):
    return connection.execute(
        text("""SELECT c.txn_id, c.amount, c.ts, v.effective_label
                FROM rails.credits c
                JOIN ledger.current_view(:merchant, :as_of) v USING (txn_id)
                WHERE c.merchant_id = :merchant AND c.ts <= :as_of
                  AND (c.ts AT TIME ZONE 'Asia/Kolkata')::date
                      BETWEEN :period_from AND :period_to
                ORDER BY c.txn_id"""),
        {
            "merchant": merchant_id,
            "as_of": as_of,
            "period_from": period_from,
            "period_to": period_to,
        },
    ).mappings().all()


def load_credit_rows_between_business_days(
    connection,
    merchant_id: str,
    as_of: datetime,
    day_from: date,
    day_to: date,
):
    return connection.execute(
        text("""SELECT c.txn_id, c.amount, c.ts, v.effective_label
                FROM rails.credits c
                JOIN ledger.current_view(:merchant, :as_of) v USING (txn_id)
                WHERE c.merchant_id = :merchant AND c.ts <= :as_of
                  AND (c.ts AT TIME ZONE 'Asia/Kolkata')::date
                      BETWEEN :day_from AND :day_to
                ORDER BY c.txn_id"""),
        {
            "merchant": merchant_id,
            "as_of": as_of,
            "day_from": day_from,
            "day_to": day_to,
        },
    ).mappings().all()


def load_billed_by_txn(connection, merchant_id: str, as_of: datetime) -> dict[str, tuple[int, int]]:
    billed_rows = connection.execute(
        text("""SELECT b.txn_id,
                       coalesce(sum(l.line_amount) FILTER (WHERE h.exempt), 0) AS exempt,
                       coalesce(sum(l.line_amount), 0) AS total
                FROM rails.bills b
                JOIN rails.bill_lines l
                  ON l.pos_bill_id = b.pos_bill_id
                 AND l.merchant_id = b.merchant_id
                 AND l.txn_id = b.txn_id
                LEFT JOIN rails.hsn_catalog h USING (item, hsn)
                WHERE b.merchant_id = :merchant AND b.sim_at <= :as_of
                GROUP BY b.txn_id
                HAVING count(l.line_no) > 0"""),
        {"merchant": merchant_id, "as_of": as_of},
    ).mappings().all()
    return {
        row["txn_id"]: (int(row["exempt"]), int(row["total"]) - int(row["exempt"]))
        for row in billed_rows
    }


def _billed_splits_for_share(rows, billed_by_txn: dict[str, tuple[int, int]]) -> tuple[int, int, int]:
    billed_exempt = 0
    billed_taxable = 0
    unbilled_total = 0
    for row in rows:
        amount = int(row["amount"])
        label = row["effective_label"]
        if label == PredictionLabel.UNCLASSIFIED.value:
            label = None
        if label in SALE_LABELS:
            bill = billed_by_txn.get(row["txn_id"])
            if bill is not None:
                billed_exempt += bill[0]
                billed_taxable += bill[1]
            else:
                unbilled_total += amount
        elif label is None:
            bill = billed_by_txn.get(row["txn_id"])
            if bill is not None:
                billed_exempt += bill[0]
                billed_taxable += bill[1]
    return billed_exempt, billed_taxable, unbilled_total


def exempt_share_for_period(rows, billed_by_txn: dict[str, tuple[int, int]]) -> float:
    billed_exempt, billed_taxable, _ = _billed_splits_for_share(rows, billed_by_txn)
    billed_sales_total = billed_exempt + billed_taxable
    return billed_exempt / billed_sales_total if billed_sales_total > 0 else 0.0


def aggregate_contribution_for_row(row, billed_by_txn: dict[str, tuple[int, int]]) -> int | None:
    amount = int(row["amount"])
    label = row["effective_label"]
    if label == PredictionLabel.UNCLASSIFIED.value:
        label = None
    if label in SALE_LABELS:
        bill = billed_by_txn.get(row["txn_id"])
        if bill is not None:
            return bill[0] + bill[1]
        return amount
    if label is None:
        bill = billed_by_txn.get(row["txn_id"])
        if bill is not None:
            return bill[0] + bill[1]
    if label is not None and not _usable_label(label):
        return None
    return None


def ordered_period_contributions(
    rows,
    billed_by_txn: dict[str, tuple[int, int]],
) -> list[tuple[date, int, str]]:
    items: list[tuple[date, int, str]] = []
    for row in rows:
        contribution = aggregate_contribution_for_row(row, billed_by_txn)
        if contribution is None or contribution == 0:
            continue
        items.append((business_day(row["ts"]), contribution, row["txn_id"]))
    items.sort(key=lambda item: (item[0], item[2]))
    return items


def first_crossing_day(
    contributions: list[tuple[date, int, str]],
    threshold: int,
    *,
    period_from: date,
    period_to: date,
) -> date | None:
    running = 0
    for day, amount, _ in contributions:
        if day < period_from or day > period_to:
            continue
        running += amount
        if running > threshold:
            return day
    return None


def trailing_window_start(as_of_day: date) -> date:
    return as_of_day - timedelta(days=59)


def sum_aggregate_in_rows(rows, billed_by_txn: dict[str, tuple[int, int]]) -> int:
    total = 0
    for row in rows:
        contribution = aggregate_contribution_for_row(row, billed_by_txn)
        if contribution is not None:
            total += contribution
    return total
