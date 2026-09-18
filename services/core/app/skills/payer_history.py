from sqlalchemy import text

from ..ledger.projection import merchant
from ..schemas.api.reads import PayerHistoryResponse


def payer_history(connection, merchant_id, counterparty, as_of):
    profile = merchant(connection, merchant_id)
    rows = connection.execute(text("""SELECT txn_id, ts, amount, channel, counterparty_name, counterparty_handle
        FROM rails.credits WHERE merchant_id = :merchant AND counterparty_id = :payer AND ts < :as_of
        ORDER BY ts DESC, txn_id DESC"""), {"merchant": merchant_id, "payer": counterparty, "as_of": as_of}).mappings().all()
    paid = connection.execute(text("""SELECT EXISTS (SELECT 1 FROM rails.debits
        WHERE merchant_id = :merchant AND counterparty_id = :payer AND ts < :as_of AND channel = 'UPI_OUT')"""),
        {"merchant": merchant_id, "payer": counterparty, "as_of": as_of}).scalar_one()
    # Facts come from ledger history so rewinding does not use a later update in ops.payer_facts.
    fact = connection.execute(text("""SELECT e.seq, e.payload->>'answer' AS answer
        FROM ledger.entries e JOIN rails.credits c ON c.txn_id = e.txn_id AND c.merchant_id = e.merchant_id
        WHERE e.merchant_id = :merchant AND c.counterparty_id = :payer
          AND e.kind = 'claim.answered' AND e.sim_at < :as_of
          AND e.payload->>'answer' IN ('family', 'own_money', 'loan_or_gift', 'refund')
        ORDER BY e.chain_index DESC LIMIT 1"""), {"merchant": merchant_id, "payer": counterparty, "as_of": as_of}).mappings().one_or_none()
    latest = rows[0] if rows else None
    owner = profile.owner_name.upper().split()
    surname = owner[-1] if owner else ""
    twins = [row["txn_id"] for row in rows[1:] if latest and row["amount"] == latest["amount"] and (latest["ts"] - row["ts"]).total_seconds() <= 1800]
    return PayerHistoryResponse(
        merchant_id=merchant_id, counterparty_id=counterparty, as_of=as_of,
        strictly_prior_credit_count=len(rows), channels=sorted({row["channel"] for row in rows}),
        merchant_has_paid_them=paid, twin_txn_ids=twins,
        own_account_cue=bool(latest and (latest["counterparty_handle"] in profile.linked_own_accounts or latest["counterparty_name"].upper() == profile.owner_name.upper())),
        surname_cue=bool(latest and surname and surname in latest["counterparty_name"].upper().split()),
        payer_facts=[{"key": "answer", "value": fact["answer"], "entry_ref": fact["seq"]}] if fact else [],
    )
