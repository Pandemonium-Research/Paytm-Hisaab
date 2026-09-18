"""End-to-end check of the four demo beats, through the real tools against the live service.

Compares tool output with the answer key in data/<split>/hidden/demo_scenario.json. This is a
test harness: nothing under service/ or tools/ reads hidden/ at runtime.

    python -m uvicorn service.app:app --port 8000     # terminal 1
    python -m tools.simulate_year --reset             # seed a year of ledger history
    python -m tools.check_beats
"""
import json
import os
import sys
from datetime import date
from pathlib import Path

from . import (build_evidence_pack, compute_aggregate_turnover, get_attestation_queue,
               isolate_disputed_credit, project_threshold_breach)

ROOT = Path(__file__).resolve().parent.parent
SPLIT = os.environ.get("HISAAB_SPLIT", "demo")
ENV = {
    "HISAAB_API": os.environ.get("HISAAB_API", "http://127.0.0.1:8000"),
    "HISAAB_KEY": os.environ.get("HISAAB_KEY", ""),
    "HISAAB_ATTEST_KEY": os.environ.get("HISAAB_ATTEST_KEY", ""),
}
FAILURES = []


def run(tool, **inputs):
    return tool.main(inputs, ENV)["output"]


def check(name, ok, detail):
    print("  %s  %-34s %s" % ("PASS" if ok else "FAIL", name, detail))
    if not ok:
        FAILURES.append(name)


def rupees(n):
    return "Rs {:,}".format(int(n or 0))


def lakh(n):
    return "Rs %.2fL" % (int(n or 0) / 100000.0)


def main():
    key = json.loads((ROOT / "data" / SPLIT / "hidden" / "demo_scenario.json").read_text(encoding="utf-8"))
    mid = key["merchant_id"]
    print("checking the four beats for %s via %s\n" % (mid, ENV["HISAAB_API"]))

    # ---- Beat 1: the ordinary Tuesday --------------------------------------------------
    print("beat 1  attestation queue asked on 10 Mar 2026, covering the weekend")
    seeded = {c["txn_id"]: c for c in key["beat1_ordinary_tuesday"]["seeded_credits"]}
    asked_on = key["beat1_ordinary_tuesday"]["attestation_date"]
    queue = run(get_attestation_queue, merchant_id=mid, date=asked_on, lookback_days=2, max_items=3)
    queued = {item["txn_id"]: item for item in queue["items"]}
    check("seeded credits surfaced", set(seeded) <= set(queued),
          "%d of %d (%s)" % (len(set(seeded) & set(queued)), len(seeded),
                             ", ".join(sorted(set(seeded) - set(queued))) or "all"))
    check("stays inside the daily budget", len(queued) <= 3,
          "%d questions covering %s (%d pending in total)"
          % (len(queued), queue["covering"], queue["pending_total"]))
    for txn_id, item in sorted(queued.items()):
        truth = seeded.get(txn_id, {}).get("true_label", "?")
        print("        %s  %-40s proposed=%s truth=%s" % (
            txn_id, item["question"][:40], item["proposed_label"], truth))

    # ---- Beat 2: the warning ------------------------------------------------------------
    print("\nbeat 2  threshold projection")
    truth_cross = date.fromisoformat(key["beat2_threshold"]["true_crossing_date"])
    as_of = key["beat2_threshold"]["replay_as_of"]
    p = run(project_threshold_breach, merchant_id=mid, as_of=as_of, fy="2025-26")
    projected = p.get("projected_crossing_date")
    if projected:
        drift = abs((date.fromisoformat(projected) - truth_cross).days)
        check("projection from %s" % as_of, drift <= 21,
              "projected %s, truth %s, %d days out, %d days of warning"
              % (projected, truth_cross, drift, p["lead_time_days"]))
    else:
        check("projection from %s" % as_of, False,
              "no crossing projected (turnover so far %s)" % lakh(p["aggregate_turnover_to_date"]))
    full = run(project_threshold_breach, merchant_id=mid, fy="2025-26")
    crossed = full.get("already_crossed_on")
    check("crossing date on full year", bool(crossed) and
          abs((date.fromisoformat(crossed) - truth_cross).days) <= 7,
          "found %s, truth %s" % (crossed, truth_cross))
    check("says registration is required", full["registration_required"] is True, full["verdict"][:80])

    # ---- Beat 3: the notice -------------------------------------------------------------
    print("\nbeat 3  turnover against the notice")
    truth = key["beat3_notice"]
    t = run(compute_aggregate_turnover, merchant_id=mid, fy="2025-26")
    computed = t["aggregate_turnover_including_provisional"]
    err = abs(computed - truth["aggregate_turnover"]) / float(truth["aggregate_turnover"])
    check("aggregate turnover", err <= 0.05,
          "computed %s vs truth %s (%.1f%% out)" % (lakh(computed), lakh(truth["aggregate_turnover"]), err * 100))
    check("gross credits match notice", t["gross_credits"] == truth["claimed_turnover"],
          "%s claimed, %s in the ledger" % (lakh(truth["claimed_turnover"]), lakh(t["gross_credits"])))
    # Understating taxable turnover is the one error this product cannot afford, so the
    # apportioned split is checked against truth, not just the total.
    split_err = abs(t["taxable_supplies"] - truth["taxable_turnover"]) / float(truth["taxable_turnover"])
    check("exempt/taxable split", split_err <= 0.25,
          "taxable %s vs truth %s (%.0f%% out); exempt %s vs %s"
          % (lakh(t["taxable_supplies"]), lakh(truth["taxable_turnover"]), split_err * 100,
             lakh(t["exempt_supplies"]), lakh(truth["exempt_turnover"])))
    pack = run(build_evidence_pack, merchant_id=mid, kind="tax", turnover=t, threshold=full)
    body = pack["pack"]
    check("tax pack assembles", bool(body.get("lines")) and body.get("difference") is not None,
          "%d lines, disputes %s of %s" % (len(body["lines"]), lakh(body["difference"]),
                                           lakh(body["claimed_turnover"])))
    for line in body["lines"]:
        print("        %-46s %12s  %s" % (line["line"], rupees(line["amount"]),
                                          "turnover" if line["counts_as_turnover"] else "excluded"))

    # ---- Beat 4: the emergency ----------------------------------------------------------
    print("\nbeat 4  isolating the disputed credit")
    b4 = key["beat4_freeze"]
    want, decoy = b4["disputed_credit"], b4["decoy_same_amount"]
    by_utr = run(isolate_disputed_credit, merchant_id=mid, utr=want["utr"])
    check("found by UTR", by_utr["matched"]["txn_id"] == want["txn_id"],
          "%s, %s of %d credits that week" % (by_utr["matched"]["txn_id"],
                                              rupees(by_utr["matched"]["amount"]), by_utr["credits_in_window"]))
    by_amount = run(isolate_disputed_credit, merchant_id=mid, amount=want["amount"],
                    date=want["ts"][:10])
    matched = (by_amount.get("matched") or {}).get("txn_id")
    check("found by amount and date", matched == want["txn_id"], "%s" % (matched or by_amount["message"][:60]))
    others = [c["txn_id"] for c in by_utr["other_payments_of_same_amount_in_window"]]
    check("decoy kept visible, not chosen", decoy["txn_id"] in others,
          "%s also took %s that week" % (decoy["txn_id"], rupees(want["amount"])))
    check("sale record has the goods", bool(by_utr["matched"]["itemised_bill"]),
          ", ".join("%s" % l["item"] for l in by_utr["matched"]["itemised_bill"]))
    fpack = run(build_evidence_pack, merchant_id=mid, kind="freeze", disputed=by_utr)
    check("freeze pack assembles", bool(fpack["pack"].get("asks")),
          fpack["pack"]["asks"][0][:70] + "...")

    print("\n%s" % ("all beats pass" if not FAILURES else "FAILED: " + ", ".join(FAILURES)))
    return 1 if FAILURES else 0


if __name__ == "__main__":
    sys.exit(main())
