"""Score provenance predictions against hidden ground truth.

    python -m synth.score data/eval data/eval/predictions_baseline.csv

The predictions CSV needs `txn_id` and `label` columns; label is one of the seven true
labels or `unclassified`. Only credits present in the file are scored, so a sample works.

Headline metrics fold taxable/exempt into "supply": that distinction decides the tax rate,
while supply vs non-supply decides turnover. Exempt vs taxable is scored separately for
POS-billed sales (identifiable per credit) and QR-only sales (only estimable in aggregate).
"""
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

from .world import SUPPLY_LABELS, TRUE_LABELS

UNC = "unclassified"


def read(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def fold(label):
    return "supply" if label in SUPPLY_LABELS else label


def main(split_dir, pred_path):
    split = Path(split_dir)
    truth = {r["txn_id"]: r for r in read(split / "hidden" / "ground_truth.csv")}
    txns = {r["txn_id"]: r for r in read(split / "visible" / "transactions.csv")}
    mtruth = json.loads((split / "hidden" / "merchant_truth.json").read_text(encoding="utf-8"))
    preds = {r["txn_id"]: r["label"].strip() for r in read(pred_path)}
    bad = {p for p in preds.values() if p not in TRUE_LABELS and p != UNC}
    if bad:
        sys.exit(f"unknown labels in predictions: {sorted(bad)}")
    scored = [(t, truth[t]["true_label"], preds[t]) for t in truth if t in preds]
    if not scored:
        sys.exit("no predicted txn_id matches a credit in this split")

    n = len(scored)
    unc = sum(p == UNC for *_, p in scored)
    prov_ok = sum(fold(y) == fold(p) for _, y, p in scored)
    wrong_committed = sum(fold(y) != fold(p) for _, y, p in scored if p != UNC)
    non_supply = [(y, p) for _, y, p in scored if y not in SUPPLY_LABELS]

    def ex_vs_tx(billed):
        pairs = [(y, p) for t, y, p in scored
                 if y in SUPPLY_LABELS and p in SUPPLY_LABELS and bool(txns[t]["pos_bill_id"]) == billed]
        return f"{sum(y == p for y, p in pairs) / len(pairs):6.1%}  (n={len(pairs)})" if pairs else "   n/a"

    print(f"scored {n} of {len(truth)} credits ({len(set(preds) - set(truth))} predictions ignored)\n")
    print("  Provenance (taxable/exempt folded into 'supply')")
    print(f"    accuracy, unclassified counts as wrong    {prov_ok / n:6.1%}")
    print(f"    selective accuracy, committed tags only   {prov_ok / max(1, n - unc):6.1%}")
    print(f"    unclassified rate                         {unc / n:6.1%}")
    print(f"    false-confidence rate, committed & wrong  {wrong_committed / n:6.1%}")
    print(f"    recall on non-supply credits              "
          f"{sum(y == p for y, p in non_supply) / max(1, len(non_supply)):6.1%}  (n={len(non_supply)})")
    print("  Exempt vs taxable")
    print(f"    POS-billed sales                          {ex_vs_tx(True)}")
    print(f"    QR-only sales                             {ex_vs_tx(False)}")
    print(f"  Exact 7-way accuracy                        {sum(y == p for _, y, p in scored) / n:6.1%}")

    print(f"\n  {'label':<18}{'support':>8}{'prec':>8}{'recall':>8}{'f1':>8}")
    for lab in TRUE_LABELS:
        tp = sum(y == lab and p == lab for _, y, p in scored)
        sup = sum(y == lab for _, y, _p in scored)
        pp = sum(p == lab for *_, p in scored)
        prec, rec = tp / pp if pp else 0.0, tp / sup if sup else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        print(f"  {lab:<18}{sup:>8}{prec:>8.2f}{rec:>8.2f}{f1:>8.2f}")

    cols = list(TRUE_LABELS) + [UNC]
    conf = Counter((y, p) for _, y, p in scored)
    print("\n  confusion (rows = truth, cols = predicted): " + " ".join(c[:6] for c in cols))
    for y in TRUE_LABELS:
        print(f"  {y:<18}" + "".join(f"{conf[(y, p)]:>7}" for p in cols))

    # Turnover is what the evidence pack asserts, so score it in rupees too.
    per_m = defaultdict(lambda: dict(n=0, ok=0, ns=0, ns_ok=0, unc=0, true_supply=0, pred_supply=0, unresolved=0))
    for t, y, p in scored:
        s, amt = per_m[truth[t]["merchant_id"]], int(txns[t]["amount"])
        s["n"] += 1
        s["ok"] += fold(y) == fold(p)
        if y not in SUPPLY_LABELS:
            s["ns"] += 1
            s["ns_ok"] += y == p
        s["unc"] += p == UNC
        s["true_supply"] += int(truth[t]["exempt_value"]) + int(truth[t]["taxable_value"])
        s["pred_supply"] += amt if p in SUPPLY_LABELS else 0
        s["unresolved"] += amt if p == UNC else 0
    print(f"\n  {'merchant':<16}{'archetype':<20}{'d':>5}{'prov':>7}{'non-sup':>9}{'unc':>6}"
          f"{'true supply':>14}{'pred supply':>14}{'unresolved':>12}")
    for mid, s in sorted(per_m.items()):
        mt = mtruth[mid]
        print(f"  {mid:<16}{mt['archetype']:<20}{mt['difficulty']:>5.2f}{s['ok'] / s['n']:>7.1%}"
              f"{s['ns_ok'] / max(1, s['ns']):>9.1%}{s['unc'] / s['n']:>6.1%}"
              f"{s['true_supply']:>14,}{s['pred_supply']:>14,}{s['unresolved']:>12,}")

    errs = Counter(truth[t]["reason"] for t, y, p in scored if p != UNC and fold(y) != fold(p))
    tot = Counter(truth[t]["reason"] for t, *_ in scored)
    print("\n  committed provenance errors by generating reason:")
    for reason, k in errs.most_common(10):
        print(f"    {reason:<45}{k:>6} / {tot[reason]}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    main(sys.argv[1], sys.argv[2])
