"""Seed a year of ledger history: what the product would have produced by demo day.

Two things happen here, and only the first is something the shipped system does:

  1. The nightly pass. Every credit goes through the same rules the Provenance agent uses
     (`classify_credit_rules._decide`) and gets a *proposed* tag.
  2. A simulated merchant. For the few credits a day the rules can't settle, a stand-in
     merchant answers, and the answer is committed as an attestation.

Step 2 reads hidden/ground_truth.csv, because a truthful merchant knows what their own money
was. That is a simulation of a person, not of a classifier: nothing in `service/` or `tools/`
may ever read hidden/. This script is not part of the runtime path.

    python -m tools.simulate_year --merchant MID_DEMO_SAHANA --reset
"""
import argparse
import csv
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from service import store
from tools.classify_credit_rules import _decide, _should_ask

ROOT = Path(__file__).resolve().parent.parent


def merchant_answers(split):
    """The stand-in merchant: txn_id -> what that credit actually was."""
    path = ROOT / "data" / split / "hidden" / "ground_truth.csv"
    if not path.exists():
        sys.exit("%s missing - run: python -m synth.generate --only %s" % (path, split))
    with open(path, encoding="utf-8") as f:
        return {r["txn_id"]: r["true_label"] for r in csv.DictReader(f)}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--merchant", default="MID_DEMO_SAHANA")
    ap.add_argument("--split", default=store.SPLIT)
    ap.add_argument("--ask-per-day", type=int, default=3, help="PLAN's attestation budget")
    ap.add_argument("--leave-pending", default="2026-03-08,2026-03-09",
                    help="days to leave un-attested so the demo can do it live")
    ap.add_argument("--reset", action="store_true", help="clear existing tags for this merchant first")
    args = ap.parse_args()

    conn = store.connect()
    store.seed(conn)
    if args.reset:
        with conn:
            conn.execute("DELETE FROM ledger WHERE merchant_id=?", (args.merchant,))

    merchant = store.merchant(conn, args.merchant)
    if not merchant:
        sys.exit("no such merchant: %s" % args.merchant)
    mix = store.mix(conn, args.merchant)
    truth = merchant_answers(args.split)

    credits = conn.execute(
        "SELECT txn_id, ts FROM txn WHERE merchant_id=? AND direction='CR' ORDER BY ts",
        (args.merchant,)).fetchall()
    print("classifying %d credits for %s ..." % (len(credits), args.merchant))

    proposals, ambiguous = [], defaultdict(list)
    now = datetime.now().isoformat(timespec="seconds")
    for row in credits:
        h = store.payer_history(conn, args.merchant, row["txn_id"])
        label, confidence, evidence, _flags = _decide(h, merchant, mix)
        ask = _should_ask(label, confidence, h)[0]
        proposals.append((row["txn_id"], args.merchant, label or "unclassified", evidence[0],
                          round(confidence, 2), "proposed", now, 1 if ask else 0))
        if ask:
            ambiguous[row["ts"][:10]].append((row["txn_id"], h["credit"]["amount"]))

    with conn:
        conn.executemany(
            "INSERT INTO ledger (txn_id, merchant_id, label, reason, confidence, status, proposed_at, ask) "
            "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(txn_id) DO UPDATE SET label=excluded.label, "
            "reason=excluded.reason, confidence=excluded.confidence, proposed_at=excluded.proposed_at, "
            "ask=excluded.ask WHERE ledger.status != 'attested'", proposals)

    # The merchant answers the biggest few each day, within the daily budget.
    pending = {d.strip() for d in (args.leave_pending or "").split(",") if d.strip()}
    asked, skipped, corrections = [], 0, 0
    for day in sorted(ambiguous):
        if day in pending:
            continue  # beat 1 happens live on stage
        todays = sorted(ambiguous[day], key=lambda x: -x[1])
        skipped += max(0, len(todays) - args.ask_per_day)
        for txn_id, _amount in todays[:args.ask_per_day]:
            answer = truth.get(txn_id)
            if not answer:
                continue
            proposed = conn.execute("SELECT label FROM ledger WHERE txn_id=?", (txn_id,)).fetchone()["label"]
            corrections += proposed != answer and proposed != "unclassified"
            asked.append((txn_id, args.merchant, answer, "merchant attestation", 1.0,
                          "attested", "merchant", "", now))
    with conn:
        conn.executemany(
            "INSERT INTO ledger (txn_id, merchant_id, label, reason, confidence, status, source, note, "
            "attested_at) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(txn_id) DO UPDATE SET "
            "label=excluded.label, status='attested', source=excluded.source, "
            "attested_at=excluded.attested_at", asked)

    days = len(ambiguous) or 1
    cov = store.coverage(conn, args.merchant)
    print("  proposed by rules      %d" % len(proposals))
    print("  asked the merchant     %d over %d days (median %.1f/day, %d beyond the daily budget)"
          % (len(asked), days, len(asked) / days, skipped))
    print("  merchant corrected     %d of those" % corrections)
    print("  attested / proposed    %d / %d" % (cov["attested"], cov["proposed"]))
    print("  rupees attested        Rs %s of Rs %s" % (cov["attested_amount"], cov["amount"]))


if __name__ == "__main__":
    main()
