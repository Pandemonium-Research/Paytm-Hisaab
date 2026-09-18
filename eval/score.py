"""Score a predictions file against the hidden truth.

    python -m eval.score data/eval data/eval/predictions_baseline.csv
    python -m eval.score data/eval my_predictions.csv --json report.json

A predictions file needs `txn_id,label`; other columns are ignored. You can score a subset: metrics
cover the credits you predicted, and turnover is only compared per merchant when every one of that
merchant's credits has a prediction.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

LABELS = ("taxable_supply", "exempt_supply", "personal_transfer", "inter_account", "non_business",
          "refund_reversal", "duplicate")
SUPPLY = ("taxable_supply", "exempt_supply")
ALLOWED = LABELS + ("unclassified",)


def _read(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def pct(num: float, den: float) -> float | None:
    return round(100.0 * num / den, 2) if den else None


def score(split: Path, predictions: Path) -> dict:
    truth = {r["txn_id"]: r for r in _read(split / "hidden" / "ground_truth.csv")}
    txns = {r["txn_id"]: r for r in _read(split / "visible" / "transactions.csv") if r["direction"] == "CR"}
    merchants = {m["merchant_id"]: m for m in json.loads((split / "hidden" / "merchant_truth.json").read_text("utf-8"))}

    preds: dict[str, str] = {}
    for row in _read(predictions):
        if row["label"] not in ALLOWED:
            raise SystemExit(f"unknown label {row['label']!r} for {row['txn_id']}")
        preds[row["txn_id"]] = row["label"]
    unknown = [tid for tid in preds if tid not in truth]
    scored = [tid for tid in preds if tid in truth]

    n = len(scored)
    committed = [tid for tid in scored if preds[tid] != "unclassified"]

    def provenance_ok(tid: str) -> bool:
        true, pred = truth[tid]["true_label"], preds[tid]
        return (true in SUPPLY and pred in SUPPLY) or pred == true

    non_supply = [tid for tid in scored if truth[tid]["true_label"] not in SUPPLY]
    supply_both = [tid for tid in scored if truth[tid]["true_label"] in SUPPLY and preds[tid] in SUPPLY]
    billed = [tid for tid in supply_both if txns[tid]["pos_bill_id"]]
    unbilled = [tid for tid in supply_both if not txns[tid]["pos_bill_id"]]

    per_label = {}
    for label in LABELS:
        tp = sum(1 for tid in scored if preds[tid] == label and truth[tid]["true_label"] == label)
        fp = sum(1 for tid in scored if preds[tid] == label and truth[tid]["true_label"] != label)
        fn = sum(1 for tid in scored if preds[tid] != label and truth[tid]["true_label"] == label)
        p, r = (tp / (tp + fp) if tp + fp else None), (tp / (tp + fn) if tp + fn else None)
        per_label[label] = dict(support=tp + fn, precision=round(p, 4) if p is not None else None,
                                recall=round(r, 4) if r is not None else None,
                                f1=round(2 * p * r / (p + r), 4) if p and r else None)

    confusion: dict[str, Counter] = defaultdict(Counter)
    for tid in scored:
        confusion[truth[tid]["true_label"]][preds[tid]] += 1

    errors = Counter(truth[tid]["reason"].split(";")[0] for tid in scored if not provenance_ok(tid))

    by_merchant = defaultdict(list)
    for tid, r in truth.items():
        by_merchant[r["merchant_id"]].append(tid)
    turnover = {}
    for mid, tids in sorted(by_merchant.items()):
        covered = [tid for tid in tids if tid in preds]
        true_supply = sum(int(txns[tid]["amount"]) for tid in covered if truth[tid]["true_label"] in SUPPLY)
        pred_supply = sum(int(txns[tid]["amount"]) for tid in covered if preds[tid] in SUPPLY)
        unresolved = sum(int(txns[tid]["amount"]) for tid in covered if preds[tid] == "unclassified")
        row = dict(credits=len(tids), predicted=len(covered), true_supply=true_supply,
                   predicted_supply=pred_supply, unresolved=unresolved,
                   error_pct=pct(pred_supply - true_supply, true_supply))
        if len(covered) == len(tids):
            mt = merchants[mid]
            threshold = mt["registration_threshold"]
            row.update(threshold=threshold, truly_above=true_supply > threshold,
                       predicted_above=pred_supply > threshold,
                       registration_answer_flips=(true_supply > threshold) != (pred_supply > threshold))
        turnover[mid] = row

    return dict(
        split=str(split), predictions=str(predictions), scored=n, total_credits=len(truth),
        coverage_pct=pct(n, len(truth)), unknown_txn_ids=len(unknown),
        provenance_accuracy_pct=pct(sum(provenance_ok(t) for t in scored), n),
        selective_accuracy_pct=pct(sum(provenance_ok(t) for t in committed), len(committed)),
        unclassified_rate_pct=pct(n - len(committed), n),
        false_confidence_rate_pct=pct(sum(not provenance_ok(t) for t in committed), len(committed)),
        non_sale=dict(count=len(non_supply),
                      recall_pct=pct(sum(preds[t] == truth[t]["true_label"] for t in non_supply), len(non_supply)),
                      false_confidence_pct=pct(sum(preds[t] not in ("unclassified", truth[t]["true_label"])
                                                   for t in non_supply), len(non_supply)),
                      counted_as_sale_pct=pct(sum(preds[t] in SUPPLY for t in non_supply), len(non_supply))),
        exempt_vs_taxable=dict(
            pos_billed_pct=pct(sum(preds[t] == truth[t]["true_label"] for t in billed), len(billed)),
            pos_billed_n=len(billed),
            qr_only_pct=pct(sum(preds[t] == truth[t]["true_label"] for t in unbilled), len(unbilled)),
            qr_only_n=len(unbilled)),
        exact_accuracy_pct=pct(sum(preds[t] == truth[t]["true_label"] for t in scored), n),
        per_label=per_label,
        confusion={k: dict(v) for k, v in sorted(confusion.items())},
        top_errors=errors.most_common(10),
        turnover=turnover,
    )


def report(r: dict) -> str:
    lines = [
        f"scored {r['scored']:,} of {r['total_credits']:,} credits ({r['coverage_pct']}%)",
        f"sale vs not-a-sale (exact type for non-sales)  {r['provenance_accuracy_pct']}%",
        f"  selective (committed only)                   {r['selective_accuracy_pct']}%",
        f"  unclassified                                 {r['unclassified_rate_pct']}%",
        f"  false confidence                             {r['false_confidence_rate_pct']}%",
        f"non-sale credits (n={r['non_sale']['count']:,})",
        f"  recall                                       {r['non_sale']['recall_pct']}%",
        f"  counted as a sale                            {r['non_sale']['counted_as_sale_pct']}%",
        f"  confidently wrong                            {r['non_sale']['false_confidence_pct']}%",
        f"exempt vs taxable: POS-billed {r['exempt_vs_taxable']['pos_billed_pct']}% "
        f"(n={r['exempt_vs_taxable']['pos_billed_n']:,}), QR-only {r['exempt_vs_taxable']['qr_only_pct']}% "
        f"(n={r['exempt_vs_taxable']['qr_only_n']:,})",
        "",
        f"{'label':<18} {'support':>8} {'precision':>10} {'recall':>8} {'f1':>8}",
    ]
    for label, v in r["per_label"].items():
        lines.append(f"{label:<18} {v['support']:>8,} {str(v['precision']):>10} {str(v['recall']):>8} {str(v['f1']):>8}")
    lines += ["", f"{'merchant':<16} {'true supply':>14} {'predicted':>14} {'error':>8} {'unresolved':>11}  registration"]
    for mid, v in r["turnover"].items():
        flip = ""
        if "registration_answer_flips" in v:
            flip = ("FLIPS: " if v["registration_answer_flips"] else "same: ") + \
                   f"truly {'above' if v['truly_above'] else 'below'} Rs {v['threshold']:,}"
        lines.append(f"{mid:<16} {v['true_supply']:>14,} {v['predicted_supply']:>14,} "
                     f"{str(v['error_pct']) + '%':>8} {v['unresolved']:>11,}  {flip}")
    lines += ["", "top errors by generating reason:"]
    lines += [f"  {count:>5}  {reason}" for reason, count in r["top_errors"]]
    lines.append(f"\nexact 7-way accuracy {r['exact_accuracy_pct']}% (don't headline it: QR exempt/taxable dominates)")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("split", type=Path)
    parser.add_argument("predictions", type=Path)
    parser.add_argument("--json", type=Path, help="also write the full report as JSON")
    args = parser.parse_args(argv)
    result = score(args.split, args.predictions)
    print(report(result))
    if args.json:
        args.json.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
