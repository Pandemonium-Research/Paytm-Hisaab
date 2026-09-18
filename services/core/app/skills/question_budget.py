from datetime import timedelta

from sqlalchemy import text

from ..ledger.mutations import day_start, validate_time
from ..ledger.projection import credit
from .payer_history import payer_history


def select_questions(connection, body):
    validate_time(connection, body.as_of)
    asked = connection.execute(text("SELECT count(*) FROM ops.questions WHERE merchant_id=:merchant AND asked_at>=:start AND asked_at<:end"),
        {"merchant": body.merchant_id, "start": day_start(body.as_of), "end": day_start(body.as_of) + timedelta(days=1)}).scalar_one()
    remaining = max(0, 3 - max(asked, body.already_asked_today))
    selected, expired, seen = [], [], set()
    proximity = 1.5 if body.threshold and abs(body.projected_turnover - body.threshold) <= body.threshold * 0.15 else 1.0
    for candidate in body.candidates:
        if candidate.txn_id in seen or candidate.proposed_at > body.as_of:
            continue
        seen.add(candidate.txn_id)
        if candidate.proposed_at + timedelta(days=7) <= body.as_of:
            expired.append(candidate.txn_id)
            continue
        payment = credit(connection, candidate.txn_id, body.as_of, body.merchant_id)
        history = payer_history(connection, body.merchant_id, payment["counterparty_id"], body.as_of)
        prior = connection.execute(text("SELECT count(*) FROM rails.credits WHERE merchant_id=:merchant AND counterparty_id=:payer AND ts<:at"),
            {"merchant": body.merchant_id, "payer": payment["counterparty_id"], "at": payment["ts"]}).scalar_one()
        has_bill = connection.execute(text("SELECT EXISTS(SELECT 1 FROM rails.bills WHERE merchant_id=:merchant AND txn_id=:txn AND sim_at<=:as_of)"),
            {"merchant": body.merchant_id, "txn": candidate.txn_id, "as_of": body.as_of}).scalar_one()
        known = candidate.payer_fact_known or bool(history.payer_facts)
        already = connection.execute(text("SELECT EXISTS(SELECT 1 FROM ops.questions WHERE merchant_id=:merchant AND txn_id=:txn AND asked_at<=:as_of)"),
            {"merchant": body.merchant_id, "txn": candidate.txn_id, "as_of": body.as_of}).scalar_one()
        sale = candidate.label is not None and candidate.label.value in {"taxable_supply", "exempt_supply"}
        eligible = candidate.label is None or candidate.confidence < 0.75 or not sale and payment["amount"] >= 10000 or sale and payment["amount"] >= 3000 and prior <= 3 and not has_bill
        if payment["amount"] < 500 or known or already or not eligible:
            continue
        selected.append((payment["amount"] * (1 - candidate.confidence) * proximity, candidate))
    selected.sort(key=lambda pair: (-pair[0], pair[1].txn_id))
    picked = sorted(selected[:remaining], key=lambda pair: (pair[1].confidence, -pair[0], pair[1].txn_id))
    return {"selected": [{"txn_id": candidate.txn_id, "payer_id": candidate.payer_id,
                           "priority": priority, "expires_at": body.as_of + timedelta(days=7)}
                         for priority, candidate in picked], "expired_txn_ids": expired,
            "remaining_daily_budget": remaining - len(picked)}
