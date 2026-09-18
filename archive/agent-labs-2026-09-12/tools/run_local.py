"""Run the tool handlers against a local (or remote) data service, exactly as Phinite will.

    python -m uvicorn service.app:app --port 8000     # in another terminal
    python -m tools.run_local            # dry run: shows the questions, commits nothing
    python -m tools.run_local --commit   # actually attests the first one

Env: HISAAB_API, HISAAB_KEY, HISAAB_ATTEST_KEY. Whatever a tool does here it will do in
Dev Studio, so if it passes here, paste it in with confidence.

The commit is opt-in because attesting a credit empties it out of the queue, which is what
`check_beats` asserts on. After a --commit run, re-seed with `simulate_year --reset`.
"""
import os
import sys

from . import (classify_credit_rules, commit_attestation, get_attestation_queue, get_credit,
               get_payer_history, propose_tag)

ENV = {
    "HISAAB_API": os.environ.get("HISAAB_API", "http://127.0.0.1:8000"),
    "HISAAB_KEY": os.environ.get("HISAAB_KEY", ""),
    "HISAAB_ATTEST_KEY": os.environ.get("HISAAB_ATTEST_KEY", ""),
}
MID = os.environ.get("HISAAB_MERCHANT", "MID_DEMO_SAHANA")
BEAT1 = ["DM0012559", "DM0012580", "DM0012583"]
FRAUD, DECOY = "DM0013171", "DM0012998"


def run(tool, **inputs):
    return tool.main(inputs, ENV)["output"]


def line(label, value):
    print("  %-22s %s" % (label, value))


def main():
    print("service:", ENV["HISAAB_API"], "\n")

    print("get_credit(DM0013171) - the disputed sale")
    c = run(get_credit, txn_id=FRAUD)
    line("amount / when", "Rs %s at %s" % (c["credit"]["amount"], c["credit"]["ts"][:16].replace("T", " ")))
    line("payer", c["credit"]["counterparty_name"])
    line("bill", ", ".join("%s" % l["item"] for l in c["bill"]["lines"]) or "(not billed)")

    print("\nget_payer_history(DM0012580) - the spouse's transfer")
    h = run(get_payer_history, merchant_id=MID, txn_id="DM0012580")
    line("summary", h["summary"])

    print("\nclassify_credit_rules over the demo credits")
    for txn in BEAT1 + [FRAUD, DECOY]:
        r = run(classify_credit_rules, merchant_id=MID, txn_id=txn)
        line(txn, "%-16s conf %.2f  ask=%-5s %s" % (
            r["label"] or "needs judgement", r["confidence"], r["ask_merchant"], r["evidence"][0][:60]))

    print("\npropose -> queue -> attest")
    for txn in BEAT1:
        r = run(classify_credit_rules, merchant_id=MID, txn_id=txn)
        p = run(propose_tag, txn_id=txn, label=r["label"] or "unclassified",
                reason=r["evidence"][0], confidence=r["confidence"], ask=r["ask_merchant"])
        line("proposed " + txn, "%s (%s)%s" % (p["tag"]["label"], p["tag"]["status"],
                                               " queued" if p["queued_for_merchant"] else ""))
    q = run(get_attestation_queue, merchant_id=MID, date="2026-03-10", lookback_days=2, max_items=3)
    for item in q["items"]:
        line("ask merchant", item["question"])
    if q["items"]:
        first = q["items"][0]
        if "--commit" in sys.argv:
            a = run(commit_attestation, txn_id=first["txn_id"], label=first["proposed_label"],
                    source="merchant", note="confirmed in run_local")
            line("committed", a.get("message") or a.get("error"))
        else:
            line("would commit", "%s as %s (pass --commit to do it for real)"
                 % (first["txn_id"], first["proposed_label"]))


if __name__ == "__main__":
    main()
