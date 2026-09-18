"""Check a generated split on disk for internal consistency.

    python -m sim.validate data/demo

Returns a list of problems (empty means valid). Reads hidden/ on purpose: it is a generator check,
not product code.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

from . import catalog as C

TXN_HEADER = ["txn_id", "merchant_id", "ts", "direction", "amount", "channel", "counterparty_id",
              "counterparty_handle", "counterparty_name", "terminal_id", "pos_bill_id", "utr",
              "orig_txn_id", "note"]
CREDIT_CHANNELS = {"UPI_QR", "UPI_POS", "CARD_POS", "UPI_INTENT", "IMPS", "BANK_TRANSFER",
                   "UPI_REVERSAL"}
DEBIT_CHANNELS = {"UPI_OUT", "REFUND"}
HIDDEN_WORDS = ("true_label", "ground_truth", "fraud_chain", "exempt_value", "counterparty_role",
                "mule", "personal_transfer", "inter_account")


def _rows(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def validate_split(root: Path) -> list[str]:
    root = Path(root)
    visible, hidden = root / "visible", root / "hidden"
    problems: list[str] = []

    def bad(msg: str):
        if len(problems) < 50:
            problems.append(msg)

    with (visible / "transactions.csv").open(newline="", encoding="utf-8") as fh:
        header = next(csv.reader(fh))
    if header != TXN_HEADER:
        bad(f"transactions.csv header is {header}")
    txns = _rows(visible / "transactions.csv")
    by_id = {t["txn_id"]: t for t in txns}
    if len(by_id) != len(txns):
        bad("duplicate txn_id")
    utrs = [t["utr"] for t in txns]
    if len(set(utrs)) != len(utrs):
        bad("duplicate utr")
    last = ""
    for t in txns:
        if len(t["utr"]) != 12 or not t["utr"].isdigit():
            bad(f"{t['txn_id']} utr {t['utr']!r}")
        if int(t["amount"]) <= 0:
            bad(f"{t['txn_id']} non-positive amount")
        channels = CREDIT_CHANNELS if t["direction"] == "CR" else DEBIT_CHANNELS
        if t["direction"] not in ("CR", "DR") or t["channel"] not in channels:
            bad(f"{t['txn_id']} {t['direction']} on channel {t['channel']}")
        if t["ts"] < last:
            bad(f"{t['txn_id']} out of time order")
        last = t["ts"]
        if t["orig_txn_id"] and t["orig_txn_id"] not in by_id:
            bad(f"{t['txn_id']} orig_txn_id {t['orig_txn_id']} missing")
        if (t["channel"] in ("UPI_POS", "CARD_POS")) != bool(t["pos_bill_id"]):
            bad(f"{t['txn_id']} bill presence does not match channel {t['channel']}")

    hsn = {(r["item"], r["hsn"]) for r in json.loads((visible / "hsn_catalog.json").read_text("utf-8"))}
    bill_totals: dict[str, int] = defaultdict(int)
    for line in _rows(visible / "pos_bill_lines.csv"):
        bill_totals[line["txn_id"]] += int(line["line_amount"])
        if (line["item"], line["hsn"]) not in hsn:
            bad(f"bill line {line['pos_bill_id']} item {line['item']} not in hsn_catalog")
    for t in txns:
        if t["pos_bill_id"] and bill_totals.get(t["txn_id"]) != int(t["amount"]):
            bad(f"{t['txn_id']} bill total {bill_totals.get(t['txn_id'])} != amount {t['amount']}")

    truth = {r["txn_id"]: r for r in _rows(hidden / "ground_truth.csv")}
    credits = [t for t in txns if t["direction"] == "CR"]
    if set(truth) != {t["txn_id"] for t in credits}:
        bad("ground_truth.csv does not cover exactly the credits")
    for tid, r in truth.items():
        if r["true_label"] not in C.LABELS:
            bad(f"{tid} label {r['true_label']}")
        value = int(r["exempt_value"]) + int(r["taxable_value"])
        expected = int(by_id[tid]["amount"]) if r["true_label"] in C.SUPPLY_LABELS else 0
        if value != expected:
            bad(f"{tid} exempt+taxable {value} != {expected}")
    for r in _rows(hidden / "relationships.csv"):
        if r["txn_id"] not in by_id or r["related_txn_id"] not in by_id:
            bad(f"relationship {r} points at a missing txn")

    merchants = json.loads((visible / "merchants.json").read_text("utf-8"))
    for m in merchants:
        mid = m["merchant_id"]
        rows = [b for b in _rows(visible / "daily_balances.csv") if b["merchant_id"] == mid]
        flows: dict[str, list[int]] = defaultdict(lambda: [0, 0])
        for t in txns:
            if t["merchant_id"] == mid:
                flows[t["ts"][:10]][0 if t["direction"] == "CR" else 1] += int(t["amount"])
        prev = None
        for b in rows:
            o, cr, dr, c = (int(b[k]) for k in ("opening_balance", "credits", "debits", "closing_balance"))
            if o + cr - dr != c:
                bad(f"{mid} {b['date']} balance does not add up")
            if c < 0:
                bad(f"{mid} {b['date']} negative closing balance {c}")
            if prev is not None and o != prev:
                bad(f"{mid} {b['date']} opening {o} != previous closing {prev}")
            if [cr, dr] != flows.get(b["date"], [0, 0]):
                bad(f"{mid} {b['date']} daily flows {cr}/{dr} != transactions {flows.get(b['date'])}")
            prev = c

    for mt in json.loads((hidden / "merchant_truth.json").read_text("utf-8")):
        mid = mt["merchant_id"]
        supply = sorted((t for t in credits if t["merchant_id"] == mid
                         and truth[t["txn_id"]]["true_label"] in C.SUPPLY_LABELS),
                        key=lambda t: t["ts"])
        agg = sum(int(t["amount"]) for t in supply)
        if agg != mt["aggregate_turnover"]:
            bad(f"{mid} aggregate turnover {agg} != truth {mt['aggregate_turnover']}")
        cum, crossing = 0, None
        for t in supply:
            cum += int(t["amount"])
            if cum > mt["registration_threshold"]:
                crossing = t["ts"][:10]
                break
        if crossing != mt["threshold_crossing_date"]:
            bad(f"{mid} crossing {crossing} != truth {mt['threshold_crossing_date']}")

    events = json.loads((visible / "rails_events.json").read_text("utf-8"))
    utr_index = {t["utr"]: t for t in txns}
    liens = {e["merchant_id"]: e["ts"] for e in events if e["type"] == "lien_marked"}
    for e in events:
        if e["type"] == "lien_marked":
            t = utr_index.get(e["disputed_utr"])
            if not t or int(t["amount"]) != e["disputed_amount"] or t["merchant_id"] != e["merchant_id"]:
                bad(f"{e['event_id']} disputed_utr does not match a credit of the disputed amount")
        if e["type"] == "lea_inquiry" and e["utr"] not in utr_index:
            bad(f"{e['event_id']} inquiry utr missing")
        if e["type"] == "payment_declined" and not (e["merchant_id"] in liens and e["ts"] >= liens[e["merchant_id"]]):
            bad(f"{e['event_id']} declined without a lien in place")
        if e["type"] == "notice_served" and not (visible / e["document"]).exists():
            bad(f"{e['event_id']} notice document missing")
    for mid, lien_ts in liens.items():
        late_debits = [t for t in txns if t["merchant_id"] == mid and t["direction"] == "DR" and t["ts"] >= lien_ts]
        if late_debits:
            bad(f"{mid} has {len(late_debits)} successful debits after the lien")

    for path in visible.rglob("*"):
        if path.suffix in (".csv", ".json"):
            text = path.read_text("utf-8").lower()
            for word in HIDDEN_WORDS:
                if word in text:
                    bad(f"visible/{path.name} contains hidden vocabulary {word!r}")
    return problems


if __name__ == "__main__":
    target = Path(sys.argv[1] if len(sys.argv) > 1 else "data/demo")
    found = validate_split(target)
    for p in found:
        print(p)
    print("valid" if not found else f"{len(found)} problem(s)")
    sys.exit(1 if found else 0)
