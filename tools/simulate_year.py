"""Seed a year of ledger history: what the product would have produced by demo day.

Two things happen here, and only the first is something the shipped system does:

  1. The nightly pass. Every credit goes through the same rules the Provenance agent uses
     (`classify_credit_rules._decide`) and gets a *proposed* tag, flagged for the merchant
     or not by the same materiality test the tool applies.
  2. A simulated merchant. For the few credits a day the rules cannot settle, a stand-in
     merchant answers, and the answer is committed as an attestation.

Step 2 reads hidden/ground_truth.csv, because a truthful merchant knows what their own
money was. That is a simulation of a person, not of a classifier: nothing in `service/` or
the published tools may ever read hidden/. This script is not part of the runtime path.

    python -m tools.simulate_year --reset

It talks to the store directly rather than over HTTP: 13k credits through the API would
take minutes, and the rules are identical either way.
"""
import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from service.store import Store
from tools.classify_credit_rules import _decide, _should_ask

ROOT = Path(__file__).resolve().parent.parent


def merchant_answers(split):
    """The stand-in merchant: txn_id -> what that credit actually was."""
    path = ROOT / "data" / split / "hidden" / "ground_truth.csv"
    if not path.exists():
        sys.exit("%s missing - run: python -m synth.generate --only %s" % (path, split))
    with open(path, encoding="utf-8") as fh:
        return {r["txn_id"]: r["true_label"] for r in csv.DictReader(fh)}


def build_context(store, merchant_id, txn, exempt_by_item):
    """The same picture the tool assembles over HTTP, straight from the store."""
    hist = store.payer_history(merchant_id, txn["counterparty_id"])
    lines = store.bill_lines.get(txn["pos_bill_id"], []) if txn["pos_bill_id"] else []
    credit = dict(txn)
    credit["bill"] = [{"item": ln["item"], "hsn": ln["hsn"], "line_amount": ln["line_amount"],
                       "exempt": exempt_by_item.get((ln["item"], ln["hsn"]), False)}
                      for ln in lines]
    credit["refunded_by"] = store.refund_for(txn["txn_id"])
    return {
        "credit": credit,
        "prior_credits": {"count": max(0, (hist.get("credit_count") or 0) - 1),
                          "total": hist.get("credit_total") or 0},
        "channels_used": sorted((hist.get("channels") or {}).keys()),
        "merchant_has_paid_this_payer": {"count": hist.get("merchant_paid_count") or 0},
        "twin_payments_within_30min": store.twins(txn["txn_id"]),
        "is_linked_own_account": bool(hist.get("handle_is_linked_own_account")),
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--merchant", default="MID_DEMO_SAHANA")
    ap.add_argument("--split", default="demo")
    ap.add_argument("--data", default="data")
    ap.add_argument("--ledger-db", default="ledger.db")
    ap.add_argument("--ask-per-day", type=int, default=3, help="PLAN's attestation budget")
    ap.add_argument("--leave-pending", default="2026-03-08,2026-03-09",
                    help="days to leave un-attested so beat 1 can happen live")
    ap.add_argument("--reset", action="store_true", help="clear existing tags for this merchant")
    args = ap.parse_args()

    store = Store(args.data, args.split, args.ledger_db)
    if args.reset:
        store.db.execute("DELETE FROM ledger WHERE merchant_id = ?", (args.merchant,))
        store.db.commit()

    merchant = store.merchants.get(args.merchant)
    if not merchant:
        sys.exit("no such merchant: %s" % args.merchant)
    mix = store.mix(args.merchant)
    truth = merchant_answers(args.split)
    exempt_by_item = {(h["item"], h["hsn"]): bool(h["exempt"])
                      for h in (store.hsn if isinstance(store.hsn, list) else [])}

    credits = sorted(store.credits_by_merchant.get(args.merchant, []), key=lambda r: r["ts"])
    print("classifying %d credits for %s ..." % (len(credits), args.merchant))

    proposals, ambiguous = [], defaultdict(list)
    now = datetime.now().isoformat(timespec="seconds")
    for txn in credits:
        h = build_context(store, args.merchant, txn, exempt_by_item)
        label, confidence, evidence, _flags = _decide(h, merchant, mix)
        ask = _should_ask(label, confidence, h)[0]
        proposals.append((txn["txn_id"], args.merchant, label or "unclassified", "proposed",
                          evidence[0], round(confidence, 2), now, 1 if ask else 0))
        if ask:
            ambiguous[txn["ts"][:10]].append((txn["txn_id"], txn["amount"]))

    store.db.executemany(
        "INSERT INTO ledger (txn_id, merchant_id, label, status, reason, confidence, proposed_at, ask)"
        " VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(txn_id) DO UPDATE SET label=excluded.label,"
        " status='proposed', reason=excluded.reason, confidence=excluded.confidence,"
        " proposed_at=excluded.proposed_at, ask=excluded.ask", proposals)
    store.db.commit()

    pending = {d.strip() for d in (args.leave_pending or "").split(",") if d.strip()}
    asked = skipped = corrections = 0
    for day in sorted(ambiguous):
        if day in pending:
            continue  # beat 1 happens live on stage
        todays = sorted(ambiguous[day], key=lambda x: -x[1])
        skipped += max(0, len(todays) - args.ask_per_day)
        for txn_id, _amount in todays[:args.ask_per_day]:
            answer = truth.get(txn_id)
            if not answer:
                continue
            proposed = store.ledger_row(txn_id)
            if proposed and proposed["label"] not in (answer, "unclassified"):
                corrections += 1
            store.attest(txn_id, answer, "merchant", "")
            asked += 1

    days = len(ambiguous) or 1
    roll = store.rollup(args.merchant)
    attested = sum(v["attested"]["amount"] for v in roll["by_label"].values())
    print("  proposed by rules      %d" % len(proposals))
    print("  asked the merchant     %d over %d days (median %.1f/day, %d beyond the daily budget)"
          % (asked, days, asked / float(days), skipped))
    print("  merchant corrected     %d of those" % corrections)
    print("  rupees attested        Rs %s of Rs %s" % (attested, roll["gross_credits"]["amount"]))
    print("  still untagged         %d credits" % roll["untagged"]["count"])


if __name__ == "__main__":
    main()
