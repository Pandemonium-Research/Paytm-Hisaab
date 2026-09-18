"""Rules-only baseline: label every credit from visible/ data alone, with no model and no merchant.

    python -m eval.baseline data/eval          # writes data/eval/predictions_baseline.csv

It is the floor the agent has to beat. Payer history is strictly prior to each credit; the only
hindsight allowed is what a nightly run at 02:00 the next day would already see (a same-day refund).
It was written by someone who knows the generator, so treat it as an optimistic floor.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

BUSINESS_WORDS = ("TRADERS", "WHOLESALE", "AGENCIES", "DISTRIBUTORS", "SUPPLIES", "FINANCE",
                  "CHIT", "INSURANCE", "LTD", "PVT", "CREDIT")
LOAN_NOTES = ("loan", "chit", "disb", "claim", "settlement", "deposit", "returned")
HOUSEHOLD_NOTES = ("kharch", "school", "gas", "rent", "amma", "maa", "aai", "for you", "ration",
                   "rashan", "selavu", "hospital", "dawai", "bijli", "kiraya", "bhade", "bhara",
                   "intiki", "khoroch")
P2P = ("UPI_INTENT", "IMPS")


def _read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def classify(split: Path) -> list[tuple[str, str, str]]:
    visible = split / "visible"
    merchants = {m["merchant_id"]: m for m in json.loads((visible / "merchants.json").read_text("utf-8"))}
    exempt_item = {(r["item"], r["hsn"]): r["exempt"]
                   for r in json.loads((visible / "hsn_catalog.json").read_text("utf-8"))}
    txns = _read(visible / "transactions.csv")
    for t in txns:
        t["_ts"] = datetime.fromisoformat(t["ts"])
        t["_amount"] = int(t["amount"])

    bill_exempt: dict[str, int] = defaultdict(int)
    for line in _read(visible / "pos_bill_lines.csv"):
        if exempt_item.get((line["item"], line["hsn"])):
            bill_exempt[line["txn_id"]] += int(line["line_amount"])

    first_paid: dict[tuple[str, str], datetime] = {}
    refund_at: dict[str, datetime] = {}
    for t in txns:
        if t["direction"] != "DR":
            continue
        if t["channel"] == "UPI_OUT":
            first_paid.setdefault((t["merchant_id"], t["counterparty_id"]), t["_ts"])
        if t["channel"] == "REFUND" and t["orig_txn_id"]:
            refund_at[t["orig_txn_id"]] = t["_ts"]

    recent: dict[tuple[str, str], list[dict]] = defaultdict(list)   # prior credits by payer
    billed_totals: dict[str, list[int]] = defaultdict(lambda: [0, 0])  # exempt, total so far
    out = []
    for t in txns:
        if t["direction"] != "CR":
            continue
        m = merchants[t["merchant_id"]]
        key = (t["merchant_id"], t["counterparty_id"])
        ts, amount, name = t["_ts"], t["_amount"], t["counterparty_name"].upper()
        note = t["note"].lower()
        cutoff = datetime.combine(ts.date() + timedelta(days=1), datetime.min.time(), ts.tzinfo) + timedelta(hours=2)
        surname = m["owner_name"].split()[-1]
        twin = next((p for p in reversed(recent[key])
                     if p["_amount"] == amount and (ts - p["_ts"]).total_seconds() <= 1800), None)

        if t["channel"] == "UPI_REVERSAL":
            label, rule = "refund_reversal", "reversal channel"
        elif t["counterparty_handle"] in m["linked_own_accounts"] or name == m["owner_name"]:
            label, rule = "inter_account", "linked own account or owner's name"
        elif key in first_paid and first_paid[key] < ts:
            label, rule = "refund_reversal", "merchant has paid this counterparty before"
        elif t["txn_id"] in refund_at and refund_at[t["txn_id"]] <= cutoff:
            label, rule = "duplicate", "refunded by the merchant"
        elif twin is not None:
            gap = (ts - twin["_ts"]).total_seconds()
            label, rule = ("duplicate", "twin within 3 minutes") if gap <= 180 else ("unclassified", "twin within 30 minutes")
        elif t["channel"] == "BANK_TRANSFER":
            label, rule = "non_business", "bank transfer"
        elif t["channel"] in P2P:
            if amount % 100 == 1 or any(w in note for w in LOAN_NOTES) or any(w in name for w in BUSINESS_WORDS):
                label, rule = "non_business", "gift amount, loan note or institution"
            elif surname.upper() in name.split() or any(w in note for w in HOUSEHOLD_NOTES):
                label, rule = "personal_transfer", "shared surname or household note"
            elif amount >= 500 and amount % 500 == 0 and (ts.hour >= 22 or ts.hour < 7):
                label, rule = "personal_transfer", "round amount at night"
            else:
                label, rule = "unclassified", "direct payment, no signal"
        elif t["pos_bill_id"]:
            label = "exempt_supply" if bill_exempt[t["txn_id"]] * 2 > amount else "taxable_supply"
            rule = "itemised bill"
        else:
            exempt_so_far, total_so_far = billed_totals[t["merchant_id"]]
            if total_so_far:
                exempt = exempt_so_far * 2 >= total_so_far
                rule = "shop's billed exempt share so far"
            else:
                category = m["category"].lower()
                exempt = any(w in category for w in ("vegetable", "fruit"))
                rule = "shop category"
            label = "exempt_supply" if exempt else "taxable_supply"

        out.append((t["txn_id"], label, rule))
        recent[key].append(t)
        if t["pos_bill_id"]:
            billed_totals[t["merchant_id"]][0] += bill_exempt[t["txn_id"]]
            billed_totals[t["merchant_id"]][1] += amount
    return out


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    split = Path(argv[0] if argv else "data/eval")
    rows = classify(split)
    target = split / "predictions_baseline.csv"
    with target.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["txn_id", "label", "rule"])
        writer.writerows(rows)
    print(f"wrote {len(rows):,} predictions to {target}")


if __name__ == "__main__":
    main()
