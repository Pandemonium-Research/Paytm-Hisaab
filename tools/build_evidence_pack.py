# ENV_VARS: ["HISAAB_API", "HISAAB_KEY"]
"""Phinite custom tool: build_evidence_pack.

Assembles the artefact the merchant hands to a CA, an officer or a bank. It composes what
other tools produced - it never recomputes a figure, and never improves one.

Two kinds:
  tax    - what the receipts actually were, against what the notice claims.
  freeze - the disputed credit, the goods sold against it, and what is being asked for.

Both carry their own limits in writing: digital receipts only, cash excluded, no assertion
of innocence, nothing filed on the merchant's behalf.

Parameters: merchant_id (string, required), kind ("tax" | "freeze", required),
reference (string, optional), turnover (object from compute_aggregate_turnover, optional),
threshold (object from project_threshold_breach, optional),
disputed (object from isolate_disputed_credit, optional).
Self-contained: paste this whole file into Dev Studio. Standard library only.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

LABEL_TEXT = {
    "taxable_supply": "Taxable sales",
    "exempt_supply": "Exempt sales (nil-rated goods)",
    "personal_transfer": "Family transfers, not business income",
    "inter_account": "Merchant's own accounts",
    "non_business": "Loan, chit payout, gift or deposit return",
    "refund_reversal": "Money returned by suppliers",
    "duplicate": "Duplicate payments (refunded)",
    "unclassified": "Not yet accounted for",
}


def _get(env, path, params=None):
    base = (env.get("HISAAB_API") or "").rstrip("/")
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"X-Hisaab-Key": env.get("HISAAB_KEY") or ""})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _obj(value):
    if isinstance(value, str) and value.strip():
        try:
            return json.loads(value)
        except ValueError:
            return {}
    return value or {}


def _rupees(n):
    return "Rs {:,}".format(int(n or 0))


def _tax_pack(merchant, notice, turnover, threshold, reference):
    claimed = (notice or {}).get("claimed_turnover")
    lines = [{"line": LABEL_TEXT.get("taxable_supply"), "amount": turnover.get("taxable_supplies", 0),
              "counts_as_turnover": True},
             {"line": LABEL_TEXT.get("exempt_supply"), "amount": turnover.get("exempt_supplies", 0),
              "counts_as_turnover": True}]
    for e in turnover.get("excluded", []):
        lines.append({"line": LABEL_TEXT.get(e["label"], e["label"]), "amount": e["amount"],
                      "counts_as_turnover": False, "why": e["why_excluded"], "payments": e["count"]})

    aggregate = turnover.get("aggregate_turnover_including_provisional", 0)
    findings = []
    if claimed:
        findings.append("The notice treats %s of digital receipts as turnover. Aggregate turnover "
                        "for the period is %s; the difference is money that is not consideration "
                        "for any supply." % (_rupees(claimed), _rupees(aggregate)))
    findings.append("Of that turnover, %s is exempt supplies and %s is taxable supplies."
                    % (_rupees(turnover.get("exempt_supplies")), _rupees(turnover.get("taxable_supplies"))))
    if threshold.get("registration_required"):
        findings.append("Aggregate turnover crossed the %s threshold on %s, so registration is due. "
                        "That is stated here because it is true, not because it is asked."
                        % (_rupees(threshold.get("threshold")), threshold.get("already_crossed_on")))
    elif threshold.get("exclusively_exempt"):
        findings.append("The shop deals exclusively in exempt goods, so no registration is required "
                        "however high turnover goes (CGST s.23).")
    return {
        "title": "Response pack: turnover reconciliation",
        "reference": reference or (notice or {}).get("reference", ""),
        "period": turnover.get("period"),
        "claimed_turnover": claimed,
        "aggregate_turnover": aggregate,
        "difference": (claimed - aggregate) if claimed else None,
        "lines": lines,
        "findings": findings,
        "workings": turnover.get("workings", []),
        "basis": ["CGST Act s.2(6): aggregate turnover is taxable plus exempt supplies.",
                  "Receipts that are not consideration for a supply are not turnover."],
    }


def _freeze_pack(merchant, freeze, disputed, reference):
    matched = (disputed or {}).get("matched") or {}
    bill = matched.get("itemised_bill") or []
    asks = [
        "Restrict any lien to the disputed amount of %s rather than the whole account, so the "
        "business can continue to pay suppliers and staff." % _rupees(matched.get("amount")),
        "Share the complaint reference and the investigating officer's details so this can be "
        "answered directly.",
    ]
    return {
        "title": "Evidence pack: disputed credit and matching sale",
        "reference": reference or ((freeze or {}).get("lea") or {}).get("case_ref", ""),
        "freeze": {"intimated_on": (freeze or {}).get("ts"),
                   "type": (freeze or {}).get("freeze_type"),
                   "authority": ((freeze or {}).get("lea") or {}).get("unit"),
                   "ncrp_ack": ((freeze or {}).get("lea") or {}).get("ncrp_ack")},
        "disputed_credit": matched,
        "sale_record": {
            "goods_sold": ", ".join("%s (HSN %s)" % (l["item"], l["hsn"]) for l in bill) or
                          "no itemised bill: this sale was a QR payment",
            "bill_total": matched.get("bill_total"),
            "till": matched.get("till"),
            "received_at": matched.get("when"),
        },
        "context": disputed.get("statement", ""),
        "other_candidates": disputed.get("other_payments_of_same_amount_in_window", []),
        "asks": asks,
        "position": "The merchant sold goods and was paid for them over UPI. Whether the payer's "
                    "money was legitimate is not something the merchant could know or verify at "
                    "the counter. This pack does not assert the payer was innocent.",
    }


def main(inputs, env_variables):
    merchant_id = (inputs.get("merchant_id") or "").strip()
    kind = (inputs.get("kind") or "").strip().lower()
    reference = (inputs.get("reference") or "").strip()
    if not merchant_id or kind not in ("tax", "freeze"):
        return {"output": {"error": 'merchant_id required and kind must be "tax" or "freeze"'},
                "captured_variables": {}}

    merchant = _get(env_variables, "/merchants/" + urllib.parse.quote(merchant_id))
    events = _get(env_variables, "/events", {"merchant_id": merchant_id})
    turnover, threshold = _obj(inputs.get("turnover")), _obj(inputs.get("threshold"))
    disputed = _obj(inputs.get("disputed"))

    if kind == "tax":
        if not turnover:
            return {"output": {"error": "run compute_aggregate_turnover first and pass its output"},
                    "captured_variables": {}}
        notice = next((e for e in events if e["type"] == "tax_notice"), None)
        body = _tax_pack(merchant, notice, turnover, threshold, reference)
        coverage = turnover.get("coverage", {})
    else:
        if not disputed.get("matched"):
            return {"output": {"error": "run isolate_disputed_credit first and pass its output"},
                    "captured_variables": {}}
        freeze = next((e for e in events if e["type"] == "account_frozen"), None)
        body = _freeze_pack(merchant, freeze, disputed, reference)
        coverage = {}

    pack = {
        "kind": kind,
        "merchant": {"merchant_id": merchant_id, "business_name": merchant.get("business_name"),
                     "owner": merchant.get("owner_name"), "gst_status": merchant.get("gst_status"),
                     "place": "%s, %s" % (merchant.get("locality"), merchant.get("city"))},
        "pack": body,
        "evidence_coverage": coverage,
        "limits": [
            "Built from digital receipts held by the payment provider. Cash sales are not included "
            "and must be added by the merchant or their CA.",
            "Every figure traces to transaction IDs in the merchant's ledger and to the merchant's "
            "own confirmation of what each payment was.",
            "This is a record, not advice, and nothing has been filed with any authority. The "
            "merchant or their CA files.",
        ],
    }
    if coverage and coverage.get("untagged"):
        pack["limits"].insert(1, "%s across %d payments is not yet accounted for and is shown as "
                                 "unresolved rather than assumed."
                              % (_rupees(coverage.get("untagged_amount")), coverage.get("untagged")))
    if coverage and coverage.get("attested_amount") is not None:
        pack["limits"].insert(1, "%s of the turnover shown is confirmed by the merchant; the rest is "
                                 "the agent's proposal awaiting confirmation."
                              % _rupees(coverage.get("attested_amount")))
    return {"output": pack, "captured_variables": {"pack_kind": kind,
                                                   "pack_reference": body.get("reference", "")}}


# Phinite injects only the variables declared in the ENV_VARS header above, so a tool
# cannot read a key it does not ask for. commit_attestation is the only tool that
# declares HISAAB_ATTEST_KEY, which is the permission boundary enforced a second way.
#
# Phinite reads one of "capture_variables" / "captured_variables" and ignores the other.
# Which one is not documented and the Dev Studio tool test echoes the return verbatim,
# so it cannot settle it. Returning both costs nothing and removes the risk of variables
# silently failing to pass between nodes.
_main = main


def main(inputs, env_variables):  # noqa: F811
    result = _main(inputs, env_variables)
    if isinstance(result, dict) and "captured_variables" in result:
        result.setdefault("capture_variables", result["captured_variables"])
    return result
