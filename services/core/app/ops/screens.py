"""M1/M2 and payment screens backed by persisted business state."""

from datetime import date

from sqlalchemy import text

from ..clock import sim_now
from ..ledger.mutations import day_start
from ..ledger.projection import merchant, read_credit, read_credits
from ..schemas.api.skills import ThresholdRequest, TurnoverRequest
from ..skills.threshold import threshold
from ..skills.turnover import turnover


def amount_text(amount):
    value = str(amount)
    tail, prefix = value[-3:], value[:-3]
    groups = []
    while prefix:
        groups.append(prefix[-2:])
        prefix = prefix[:-2]
    return "₹" + ",".join([*reversed(groups), tail])


def open_questions(connection, merchant_id, as_of):
    return connection.execute(text("""SELECT q.*, c.amount, c.ts, c.counterparty_name, c.channel
        FROM ops.questions q JOIN rails.credits c ON c.txn_id = q.txn_id AND c.merchant_id = q.merchant_id
        WHERE q.merchant_id = :merchant AND q.asked_at <= :as_of AND q.expires_at > :as_of
          AND c.ts <= :as_of AND NOT EXISTS (SELECT 1 FROM ledger.entries e
            WHERE e.merchant_id = q.merchant_id AND e.kind = 'claim.answered' AND e.sim_at <= :as_of
              AND e.payload->>'question_id' = q.question_id)
        ORDER BY q.asked_at, q.entry_ref"""), {"merchant": merchant_id, "as_of": as_of}).mappings().all()


def home(connection, merchant_id):
    profile, as_of = merchant(connection, merchant_id), sim_now(connection)
    questions = open_questions(connection, merchant_id, as_of)
    sums = connection.execute(text("""SELECT
        coalesce((SELECT sum(amount) FROM rails.credits WHERE merchant_id = :merchant AND ts <= :as_of), 0) AS received,
        coalesce((SELECT sum(amount) FROM rails.debits WHERE merchant_id = :merchant AND ts <= :as_of), 0) AS paid,
        coalesce((SELECT sum(amount) FROM rails.credits WHERE merchant_id = :merchant AND ts >= :start AND ts <= :as_of), 0) AS today"""),
        {"merchant": merchant_id, "as_of": as_of, "start": day_start(as_of)}).mappings().one()
    opening = connection.execute(text("SELECT data FROM ops.settings WHERE key = :key"), {"key": f"opening_balance:{merchant_id}"}).scalar_one_or_none()
    balance = max(0, (opening or {}).get("amount", 0) + int(sums["received"]) - int(sums["paid"]))
    cases = connection.execute(text("SELECT count(*) FROM ops.cases WHERE merchant_id = :merchant AND status <> 'closed' AND opened_at <= :as_of"), {"merchant": merchant_id, "as_of": as_of}).scalar_one()
    return {"merchant_id": merchant_id, "business_name": profile.business_name, "as_of": as_of,
        "balance": {"amount": balance, "amount_text": amount_text(balance)},
        "today_received": {"amount": int(sums["today"]), "amount_text": amount_text(int(sums["today"]))},
        "questions_due": len(questions), "open_cases": cases,
        "alerts": [{"kind": "question", "title": f"{len(questions)} payments to confirm",
                    "body": "Tell us what these payments were for.", "href": "/merchant/confirm"}] if questions else []}


def questions(connection, merchant_id):
    merchant(connection, merchant_id)
    as_of = sim_now(connection)
    rows = open_questions(connection, merchant_id, as_of)
    chips = [{"answer": answer, "text": title} for answer, title in
        (("sale", "Sale"), ("family", "Family"), ("own_money", "My own money"),
         ("loan_or_gift", "Loan / other"), ("not_sure", "Not sure"))]
    items = [{"question_id": row["question_id"], "txn_id": row["txn_id"], "amount": row["amount"],
        "amount_text": amount_text(row["amount"]), "ts": row["ts"], "payer_name": row["counterparty_name"],
        "channel": row["channel"], "question": row["data"]["text"], "language": row["data"]["language"],
        "answer_chips": chips, "position": index + 1, "total": len(rows)} for index, row in enumerate(rows)]
    # Counted by when the label was recorded, not when the payment arrived: the nightly run
    # classifies the days *before* it, so dating this by the credit counted only payments made
    # after the run and always read zero.
    settled = connection.execute(text("""SELECT count(DISTINCT e.txn_id) FROM ledger.entries e
        JOIN rails.credits c ON c.txn_id = e.txn_id AND c.merchant_id = e.merchant_id
        WHERE e.merchant_id = :merchant AND e.kind = 'label.proposed'
          AND e.sim_at >= :start AND e.sim_at <= :as_of AND NOT EXISTS (
              SELECT 1 FROM ops.questions q WHERE q.merchant_id = e.merchant_id AND q.txn_id = e.txn_id
                AND q.asked_at <= :as_of)"""), {"merchant": merchant_id, "as_of": as_of, "start": day_start(as_of)}).scalar_one()
    return {"items": items, "automatically_settled_count": settled,
            "closing_text": "All payments confirmed." if not rows else "At most three questions a day."}


def payment_row(item, needs_answer=False):
    transaction = item.transaction
    return {"txn_id": transaction.txn_id, "ts": transaction.ts, "counterparty_name": transaction.counterparty_name,
        "amount": transaction.amount, "amount_text": amount_text(transaction.amount),
        "channel": transaction.channel.value, "effective_label": item.effective_label, "needs_answer": needs_answer}


def payments(connection, merchant_id, limit, cursor):
    as_of = sim_now(connection)
    items, next_cursor = read_credits(connection, merchant_id, as_of, limit, cursor, descending=True)
    pending = {row["txn_id"] for row in open_questions(connection, merchant_id, as_of)}
    return {"items": [payment_row(item, item.transaction.txn_id in pending) for item in items], "next_cursor": next_cursor}


def payment_detail(connection, merchant_id, txn_id):
    as_of = sim_now(connection)
    item = read_credit(connection, txn_id, as_of)
    if item.transaction.merchant_id != merchant_id:
        from fastapi import HTTPException
        raise HTTPException(404, "Payment not found for this merchant.")
    pending = {row["txn_id"] for row in open_questions(connection, merchant_id, as_of)}
    return {**payment_row(item, txn_id in pending), "utr": item.transaction.utr, "note": item.transaction.note,
        "machine_label": item.machine_label, "claim_label": item.claim_label, "conflict": item.conflict, "evidence": []}


def financial_year(as_of):
    """India's financial year runs 1 April to 31 March; a March date belongs to the year before."""
    day = as_of.date()
    start_year = day.year if day.month >= 4 else day.year - 1
    return date(start_year, 4, 1), date(start_year + 1, 3, 31), f"FY {start_year}-{str(start_year + 1)[-2:]}"


def turnover_screen(connection, merchant_id):
    """M7: the real aggregate against the threshold, not a fixture. Wraps 6.2 and 6.3."""
    profile, as_of = merchant(connection, merchant_id), sim_now(connection)
    period_from, period_to, period = financial_year(as_of)
    figures = turnover(connection, TurnoverRequest(
        merchant_id=merchant_id, period_from=period_from, period_to=period_to, as_of=as_of))
    verdict = threshold(connection, ThresholdRequest(
        merchant_id=merchant_id, period_from=period_from, period_to=period_to, as_of=as_of,
        supply_kind=profile.supply_kind, gst_status=profile.gst_status,
        aggregate_turnover=figures.aggregate,
        exclusively_exempt=figures.taxable == 0 and figures.exempt > 0))
    estimated = figures.estimated_unbilled_taxable + figures.estimated_unbilled_exempt
    explanation = "Aggregate turnover includes taxable and exempt supplies."
    if estimated:
        explanation += f" {amount_text(estimated)} is estimated from sales without an itemised bill."
    if figures.coverage_fraction < 1:
        explanation += (f" {round(figures.coverage_fraction * 100)}% of the period's payments carry"
                        " a recorded label; the rest are not counted yet.")
    return {"period": period, "aggregate": figures.aggregate, "aggregate_text": amount_text(figures.aggregate),
            "threshold": verdict.threshold, "threshold_text": amount_text(verdict.threshold),
            "bands": [{"label": label, "amount": amount, "amount_text": amount_text(amount)}
                      for label, amount in (("Taxable", figures.taxable), ("Exempt", figures.exempt))],
            "crossed_on": verdict.crossed_on, "projected_crossing_on": verdict.projected_crossing_on,
            "registration_required": verdict.registration_required, "explanation": explanation}
