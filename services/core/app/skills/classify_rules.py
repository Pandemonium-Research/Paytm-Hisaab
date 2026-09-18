"""Observable payment rules; uncertain direct payments remain hard cases for the agent."""

from sqlalchemy import text

from ..ledger.mutations import validate_time
from ..ledger.projection import credit, merchant


HOUSEHOLD_NOTES = ("family", "school", "kharch", "amma", "maa", "rent", "ration", "hospital")
LOAN_NOTES = ("loan", "chit", "disb", "deposit", "insurance", "gift")


def classify(connection, body):
    validate_time(connection, body.as_of)
    profile = merchant(connection, body.merchant_id)
    billed = connection.execute(text("""SELECT coalesce(sum(l.line_amount) FILTER (WHERE h.exempt), 0) AS exempt,
        coalesce(sum(l.line_amount), 0) AS total FROM rails.bill_lines l
        JOIN rails.bills b USING (pos_bill_id) LEFT JOIN rails.hsn_catalog h USING (item, hsn)
        WHERE b.merchant_id = :merchant AND b.sim_at <= :as_of"""),
        {"merchant": body.merchant_id, "as_of": body.as_of}).mappings().one()
    shop_exempt = (billed["exempt"] * 2 > billed["total"] if billed["total"] else
                   any(word in profile.category.lower() for word in ("vegetable", "fruit")))
    results = []
    for supplied in body.credits:
        payment = credit(connection, supplied.txn_id, body.as_of, body.merchant_id)
        values = {"merchant": body.merchant_id, "payer": payment["counterparty_id"],
                  "as_of": body.as_of, "at": payment["ts"], "txn": supplied.txn_id, "amount": payment["amount"]}
        features = connection.execute(text("""SELECT
            (SELECT count(*) FROM rails.credits WHERE merchant_id=:merchant AND counterparty_id=:payer AND ts<:at) AS prior,
            EXISTS(SELECT 1 FROM rails.debits WHERE merchant_id=:merchant AND counterparty_id=:payer AND channel='UPI_OUT' AND ts<:at) AS paid,
            EXISTS(SELECT 1 FROM rails.debits WHERE merchant_id=:merchant AND channel='REFUND' AND orig_txn_id=:txn AND ts<=:as_of) AS refunded,
            (SELECT extract(epoch FROM (:at - ts)) FROM rails.credits
                WHERE merchant_id=:merchant AND counterparty_id=:payer AND amount=:amount AND ts<:at
                  AND ts >= :at - interval '30 minutes' ORDER BY ts DESC LIMIT 1) AS twin_gap"""), values).mappings().one()
        bill = connection.execute(text("""SELECT coalesce(sum(l.line_amount) FILTER (WHERE h.exempt), 0) AS exempt,
            sum(l.line_amount) AS total FROM rails.bill_lines l JOIN rails.bills b USING (pos_bill_id)
            LEFT JOIN rails.hsn_catalog h USING (item, hsn)
            WHERE b.txn_id=:txn AND b.merchant_id=:merchant AND b.sim_at<=:as_of"""), values).mappings().one()
        fact = connection.execute(text("""SELECT e.payload->>'answer' FROM ledger.entries e
            JOIN rails.credits c ON c.txn_id=e.txn_id AND c.merchant_id=e.merchant_id
            WHERE e.merchant_id=:merchant AND c.counterparty_id=:payer AND e.kind='claim.answered'
              AND e.sim_at<:at AND e.payload->>'answer' IN ('family','own_money','loan_or_gift','refund')
            ORDER BY e.chain_index DESC LIMIT 1"""), values).scalar_one_or_none()
        name, note = payment["counterparty_name"].upper(), payment["note"].lower()
        label, confidence, rule, reason = None, 0.0, "", ""
        if payment["channel"] == "UPI_REVERSAL":
            label, confidence, rule, reason = "refund_reversal", 1.0, "reversal", "The payment rail identifies a reversal."
        elif features["refunded"]:
            label, confidence, rule, reason = "duplicate", 1.0, "linked-refund", "A refund references this payment."
        elif payment["counterparty_handle"] in profile.linked_own_accounts or name == profile.owner_name.upper():
            label, confidence, rule, reason = "inter_account", 1.0, "own-account", "The payer matches a linked own account or the owner's name."
        elif features["paid"]:
            label, confidence, rule, reason = "refund_reversal", 0.9, "prior-payment", "The merchant paid this counterparty before this credit."
        elif bill["total"]:
            label = "exempt_supply" if bill["exempt"] * 2 > bill["total"] else "taxable_supply"
            confidence, rule, reason = 1.0, "itemised-bill", "The linked bill provides the supply classification."
        elif fact:
            label = {"family": "personal_transfer", "own_money": "inter_account", "loan_or_gift": "non_business", "refund": "refund_reversal"}[fact]
            confidence, rule, reason = 0.9, "payer-answer", "The merchant previously identified this payer's relationship."
        elif features["twin_gap"] is not None:
            if features["twin_gap"] <= 180:
                label, confidence, rule, reason = "duplicate", 0.8, "close-twin", "A same-payer, same-amount credit preceded this within three minutes, without a separate bill."
        elif payment["channel"] == "BANK_TRANSFER" or any(word in note for word in LOAN_NOTES):
            label, confidence, rule, reason = "non_business", 0.9, "nonbusiness-cue", "The rail or payment note indicates non-business money."
        elif payment["channel"] == "UPI_QR" and profile.owner_name.upper().split()[-1] in name.split():
            label, confidence, rule, reason = "personal_transfer", 0.65, "household-qr-cue", "A shared surname on a shop QR payment needs merchant confirmation."
        elif payment["channel"] in {"IMPS", "UPI_INTENT"}:
            surname = profile.owner_name.upper().split()[-1]
            if surname in name.split() or any(word in note for word in HOUSEHOLD_NOTES):
                label, confidence, rule, reason = "personal_transfer", 0.8, "household-cue", "A surname or household note suggests a family transfer."
            elif payment["amount"] >= 500 and payment["amount"] % 500 == 0 and (payment["ts"].hour >= 22 or payment["ts"].hour < 7):
                label, confidence, rule, reason = "personal_transfer", 0.65, "night-transfer", "A round direct transfer at night needs confirmation."
        else:
            label = "exempt_supply" if shop_exempt else "taxable_supply"
            confidence, rule, reason = 0.9, "shop-supply", "A merchant payment uses the shop's visible billed mix or category."
        result = None
        if label is not None:
            sale = label in {"taxable_supply", "exempt_supply"}
            ask = payment["amount"] >= 500 and not fact and (
                confidence < 0.75 or not sale and payment["amount"] >= 10000 or
                sale and payment["amount"] >= 3000 and features["prior"] <= 3 and not bill["total"])
            result = {"txn_id": supplied.txn_id, "label": label, "confidence": confidence,
                      "rule_id": rule, "ask": bool(ask), "reason": reason}
        results.append({"txn_id": supplied.txn_id, "result": result})
    return {"results": results}
