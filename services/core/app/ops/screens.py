"""M1/M2 and payment screens backed by persisted business state."""

from sqlalchemy import text

from ..clock import sim_now
from ..ledger.mutations import day_start
from ..ledger.projection import merchant, read_credit, read_credits


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
    settled = connection.execute(text("""SELECT count(*) FROM ledger.current_view(:merchant, :as_of) v
        JOIN rails.credits c USING (txn_id) WHERE c.merchant_id = :merchant
          AND c.ts >= :start AND v.machine_label IS NOT NULL AND NOT EXISTS (
              SELECT 1 FROM ops.questions q WHERE q.merchant_id = :merchant AND q.txn_id = c.txn_id
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
