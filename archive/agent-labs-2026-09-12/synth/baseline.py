"""A deliberately simple rule baseline that reads visible/ only.

It exists to prove the labels are recoverable from visible signals and that the
difficulty knob bites. It is the floor the Provenance Agent has to beat, not the product.

    python -m synth.baseline data/eval      # writes data/eval/predictions_baseline.csv
"""
import csv
import json
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

P2P = ("UPI_INTENT", "IMPS")
NON_BUSINESS_WORDS = ("loan", "chit", "advance", "claim", "disb")


def read(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def main(split_dir):
    split = Path(split_dir)
    rows = read(split / "visible" / "transactions.csv")
    merchants = {m["merchant_id"]: m for m in json.loads((split / "visible" / "merchants.json").read_text(encoding="utf-8"))}
    catalog = json.loads((split.parent / "reference" / "hsn_catalog.json").read_text(encoding="utf-8"))
    exempt_item = {(c["item"], c["hsn"]): c["exempt"] for c in catalog}

    bills = defaultdict(list)
    for b in read(split / "visible" / "pos_bill_lines.csv"):
        bills[b["txn_id"]].append((exempt_item[(b["item"], b["hsn"])], int(b["line_amount"])))
    # Exempt share of billed value per merchant, used as a prior for un-billed QR sales.
    ex_share = defaultdict(lambda: [0, 0])
    by_txn_merchant = {r["txn_id"]: r["merchant_id"] for r in rows}
    for t, lines in bills.items():
        s = ex_share[by_txn_merchant[t]]
        s[0] += sum(v for e, v in lines if e)
        s[1] += sum(v for _, v in lines)

    for r in rows:
        r["t"], r["amt"] = datetime.fromisoformat(r["ts"]), int(r["amount"])
    refunded = {r["orig_txn_id"] for r in rows if r["channel"] == "REFUND"}
    paid = defaultdict(set)
    for r in rows:
        if r["direction"] == "DR" and r["channel"] == "UPI_OUT":
            paid[r["merchant_id"]].add(r["counterparty_id"])
    recent = defaultdict(list)  # (merchant, payer, amount) -> earlier credit rows

    out = []
    for r in rows:
        if r["direction"] != "CR":
            continue
        m = merchants[r["merchant_id"]]
        owner_surname = m["owner_name"].split()[-1]
        name, note = r["counterparty_name"], r["note"].lower()
        key = (r["merchant_id"], r["counterparty_id"], r["amt"])
        twins = [x for x in recent[key] if r["t"] - x["t"] <= timedelta(minutes=30)]
        recent[key].append(r)

        if r["channel"] == "UPI_REVERSAL":
            lab, why = "refund_reversal", "reversal channel"
        elif r["counterparty_handle"] in m["linked_own_accounts"] or name == m["owner_name"]:
            lab, why = "inter_account", "own account"
        elif r["counterparty_id"] in paid[r["merchant_id"]]:
            lab, why = "refund_reversal", "payer is someone we paid"
        elif r["txn_id"] in refunded:
            lab, why = "duplicate", "refunded"
        elif twins and not any(x["txn_id"] in refunded for x in twins):
            gap = r["t"] - twins[-1]["t"]
            lab, why = ("duplicate", "twin < 3 min") if gap <= timedelta(minutes=3) else ("unclassified", "twin 3-30 min")
        elif r["channel"] == "BANK_TRANSFER":
            lab, why = "non_business", "bank transfer"
        elif r["channel"] in P2P:
            if r["amt"] % 100 == 1 or any(w in note for w in NON_BUSINESS_WORDS):
                lab, why = "non_business", "gift amount / note"
            elif owner_surname in name or note:
                lab, why = "personal_transfer", "surname or note"
            elif r["amt"] % 500 == 0 and (r["t"].hour >= 21 or r["t"].hour < 7):
                lab, why = "personal_transfer", "round & off-hours"
            else:
                lab, why = "unclassified", "p2p, no cue"
        elif r["txn_id"] in bills:
            ex = sum(v for e, v in bills[r["txn_id"]] if e)
            lab, why = ("exempt_supply" if ex * 2 > r["amt"] else "taxable_supply"), "pos bill hsn"
        else:
            e, tot = ex_share[r["merchant_id"]]
            share = e / tot if tot else (1.0 if "vegetable" in m["category"].lower() else 0.0)
            lab, why = ("exempt_supply" if share > 0.5 else "taxable_supply"), "merchant prior"
        out.append((r["txn_id"], lab, why))

    path = split / "predictions_baseline.csv"
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["txn_id", "label", "rule"])
        w.writerows(out)
    print(f"wrote {len(out)} predictions to {path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
