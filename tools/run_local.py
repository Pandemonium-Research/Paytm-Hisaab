"""Run the tool handlers against a local (or remote) data service, exactly as Phinite will.

    python -m uvicorn service.app:app --port 8000     # in another terminal
    python -m tools.run_local

Env: HISAAB_API, HISAAB_KEY, HISAAB_ATTEST_KEY. Anything a tool does here it will do in
Dev Studio, so if it passes here, paste it in with confidence.
"""
import json
import os

from . import (classify_credit_rules, commit_attestation, get_attestation_queue, get_credit,
               get_payer_history, propose_tag)

ENV = {
    "HISAAB_API": os.environ.get("HISAAB_API", "http://127.0.0.1:8000"),
    "HISAAB_KEY": os.environ.get("HISAAB_KEY", ""),
    "HISAAB_ATTEST_KEY": os.environ.get("HISAAB_ATTEST_KEY", ""),
}
MID = os.environ.get("HISAAB_MERCHANT", "MID_DEMO_SAHANA")
# Beat 1 (own savings, spouse, bulk sale), beat 4 (fraud credit, decoy), and a plain QR sale.
BEAT1 = ["DM0012559", "DM0012580", "DM0012583"]
FRAUD, DECOY = "DM0013171", "DM0012998"


def run(tool, **inputs):
    return tool.main(inputs, ENV)["output"]


def line(label, value):
    print("  %-22s %s" % (label, value))


def main():
    print("service:", ENV["HISAAB_API"], "\n")

    print("get_credit(DM0012583)")
    c = run(get_credit, txn_id="DM0012583")
    line("amount / when", "Rs %s at %s" % (c["amount"], c["ts"][:16].replace("T", " ")))
    line("payer", c["counterparty_name"])
    line("bill", c["bill_summary"]["items"] or "(no itemised bill)")

    print("\nget_payer_history(spouse credit DM0012580)")
    h = run(get_payer_history, merchant_id=MID, txn_id="DM0012580")
    line("summary", h["summary"])

    print("\nclassify_credit_rules over the demo credits")
    for txn in BEAT1 + [FRAUD, DECOY]:
        r = run(classify_credit_rules, merchant_id=MID, txn_id=txn)
        line(txn, "%-16s conf %.2f  ask=%s  %s" % (
            r["label"] or "needs judgement", r["confidence"], r["ask_merchant"], r["evidence"][0]))

    print("\npropose_tag + queue + commit_attestation")
    for txn in BEAT1:
        r = run(classify_credit_rules, merchant_id=MID, txn_id=txn)
        p = run(propose_tag, txn_id=txn, label=r["label"] or "unclassified",
                reason=r["evidence"][0], confidence=r["confidence"])
        line("proposed " + txn, "%s (%s)" % (p["tag"]["label"], p["tag"]["status"]))
    q = run(get_attestation_queue, merchant_id=MID, day="2026-03-09", max_items=3)
    for item in q["items"]:
        line("ask merchant", item["question"])
    if q["items"]:
        first = q["items"][0]
        a = run(commit_attestation, txn_id=first["txn_id"], label=first["proposed_label"],
                source="merchant", note="confirmed in demo")
        line("committed", json.dumps(a["tag"], separators=(",", ":")) if a.get("tag") else a)


if __name__ == "__main__":
    main()
