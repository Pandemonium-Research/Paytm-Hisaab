"""Real proposal/question/claim writes, sharing one request transaction with ops state."""

from datetime import timedelta
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import text

from ..clock import sim_now
from ..schemas.api.ledger_ops import ClaimAction
from ..schemas.ledger import EntryKind, LedgerEntry
from .chain import append, lock_head
from .projection import credit, merchant


BUSINESS_ZONE = ZoneInfo("Asia/Kolkata")


def business_day(value):
    return value.astimezone(BUSINESS_ZONE).date()


def day_start(value):
    return value.astimezone(BUSINESS_ZONE).replace(hour=0, minute=0, second=0, microsecond=0)


def wire_entry(entry):
    """Wire hashes are hex strings; stored and internal hashes remain raw SHA-256 bytes."""
    entry = entry.root if isinstance(entry, LedgerEntry) else entry
    result = entry.model_dump(mode="python")
    result["hash"], result["prev_hash"] = entry.hash.hex(), entry.prev_hash.hex()
    return result


def existing_entry(connection, seq):
    row = connection.execute(text("SELECT * FROM ledger.entries WHERE seq = :seq"), {"seq": seq}).mappings().one()
    return LedgerEntry.model_validate(dict(row))


def validate_time(connection, value):
    if value > sim_now(connection):
        raise HTTPException(422, "Use the business time from /app/home.as_of; advance /sim/clock before future writes.")


def proposal(connection, body, role):
    validate_time(connection, body.sim_at)
    merchant(connection, body.merchant_id)
    credit(connection, body.txn_id, body.sim_at, body.merchant_id)
    return append(connection, merchant_id=body.merchant_id, txn_id=body.txn_id,
        kind=EntryKind.LABEL_PROPOSED, payload=body.proposal, actor_role=role, actor_ref="api", sim_at=body.sim_at)


def question(connection, body, role):
    validate_time(connection, body.sim_at)
    credit(connection, body.txn_id, body.sim_at, body.merchant_id)
    if body.question.expires_at <= body.sim_at or body.question.expires_at > body.sim_at + timedelta(days=7):
        raise HTTPException(422, "Questions expire after at most seven days.")
    lock_head(connection, body.merchant_id)
    existing = connection.execute(text("SELECT * FROM ops.questions WHERE question_id = :question"), {"question": body.question.question_id}).mappings().one_or_none()
    if existing:
        if existing["merchant_id"] != body.merchant_id or existing["txn_id"] != body.txn_id or existing["data"] != body.question.model_dump(mode="json"):
            raise HTTPException(409, "That question ID is already in use for different content.")
        return existing_entry(connection, existing["entry_ref"])
    count = connection.execute(text("""SELECT count(*) FROM ops.questions
        WHERE merchant_id = :merchant AND asked_at >= :start AND asked_at < :end"""),
        {"merchant": body.merchant_id, "start": day_start(body.sim_at), "end": day_start(body.sim_at) + timedelta(days=1)}).scalar_one()
    if count >= 3:
        raise HTTPException(409, "This merchant has already been asked three questions today.")
    entry = append(connection, merchant_id=body.merchant_id, txn_id=body.txn_id,
        kind=EntryKind.QUESTION_ASKED, payload=body.question, actor_role=role, actor_ref="api", sim_at=body.sim_at)
    connection.execute(text("""INSERT INTO ops.questions
        (question_id, merchant_id, txn_id, entry_ref, asked_at, expires_at, data)
        VALUES (:question, :merchant, :txn, :entry, :asked, :expires, CAST(:data AS jsonb))"""),
        {"question": body.question.question_id, "merchant": body.merchant_id, "txn": body.txn_id,
         "entry": entry.root.seq, "asked": body.sim_at, "expires": body.question.expires_at,
         "data": body.question.model_dump_json()})
    return entry


def claim(connection, body, role):
    validate_time(connection, body.sim_at)
    transaction = credit(connection, body.txn_id, body.sim_at, body.merchant_id)
    lock_head(connection, body.merchant_id)
    updated = False
    if body.action is ClaimAction.ANSWER:
        question = connection.execute(text("SELECT * FROM ops.questions WHERE question_id = :question"), {"question": body.claim.question_id}).mappings().one_or_none()
        if question is None or question["merchant_id"] != body.merchant_id or question["txn_id"] != body.txn_id:
            raise HTTPException(404, "The question does not belong to this payment and merchant.")
        existing = connection.execute(text("""SELECT * FROM ledger.entries WHERE merchant_id = :merchant
            AND kind = 'claim.answered' AND payload->>'question_id' = :question
            ORDER BY chain_index DESC LIMIT 1"""), {"merchant": body.merchant_id, "question": body.claim.question_id}).mappings().one_or_none()
        if existing:
            if existing["payload"] != body.claim.model_dump(mode="json"):
                raise HTTPException(409, "This question was already answered; use an annotation to correct it.")
            return LedgerEntry.model_validate(dict(existing)), body.claim.answer.value in {"family", "own_money", "loan_or_gift", "refund"}
        if body.sim_at < question["asked_at"] or body.sim_at >= question["expires_at"]:
            raise HTTPException(409, "This question is not open at that business time.")
        kind = EntryKind.CLAIM_ANSWERED
    else:
        kind = EntryKind.CLAIM_ANNOTATED if body.action is ClaimAction.ANNOTATE else EntryKind.LABEL_DISPUTED
    entry = append(connection, merchant_id=body.merchant_id, txn_id=body.txn_id,
        kind=kind, payload=body.claim, actor_role=role, actor_ref="api", sim_at=body.sim_at)
    if body.action is ClaimAction.ANSWER:
        connection.execute(text("UPDATE ops.questions SET status = 'answered' WHERE question_id = :question"), {"question": body.claim.question_id})
        if body.claim.answer.value in {"family", "own_money", "loan_or_gift", "refund"}:
            connection.execute(text("""INSERT INTO ops.payer_facts
                (merchant_id, counterparty_id, key, value, entry_ref, sim_at)
                VALUES (:merchant, :payer, 'answer', :answer, :entry, :as_of)
                ON CONFLICT (merchant_id, counterparty_id, key) DO UPDATE
                SET value = excluded.value, entry_ref = excluded.entry_ref, sim_at = excluded.sim_at"""),
                {"merchant": body.merchant_id, "payer": transaction["counterparty_id"],
                 "answer": body.claim.answer.value, "entry": entry.root.seq, "as_of": body.sim_at})
            updated = True
    return entry, updated
