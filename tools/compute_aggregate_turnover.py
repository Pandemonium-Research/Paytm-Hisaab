"""Phinite custom tool: compute_aggregate_turnover.

Aggregate turnover under CGST s.2(6) = taxable supplies + exempt supplies. Money that is not
a supply - family transfers, the merchant's own accounts, loans and chit payouts, duplicates,
refunds - is excluded and shown separately, because the whole argument with a notice is about
that difference.

Attested tags and merely proposed ones are reported apart. An evidence pack may quote the
attested figure; the provisional one is for the merchant's own planning.

Parameters: merchant_id (string, required), start (YYYY-MM-DD, optional),
end (YYYY-MM-DD, optional), fy (string like "2025-26", optional - sets start/end).
Self-contained: paste this whole file into Dev Studio. Standard library only.
"""
import json
import urllib.parse
import urllib.request

SUPPLY = ("taxable_supply", "exempt_supply")
EXCLUDED_BECAUSE = {
    "personal_transfer": "money from family, not consideration for a supply",
    "inter_account": "the merchant's own money moving between their accounts",
    "non_business": "loan, chit payout, gift or deposit return - not a supply",
    "refund_reversal": "money returned by a supplier, not a receipt from a customer",
    "duplicate": "the same sale paid twice; the duplicate was refunded",
    "unclassified": "not yet accounted for",
}


def _api(env, path, params=None, body=None, key="HISAAB_KEY"):
    base = (env.get("HISAAB_API") or "http://127.0.0.1:8000").rstrip("/")
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                 headers={"X-API-Key": env.get(key) or "", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def fy_window(fy):
    start_year = int(str(fy).split("-")[0])
    return "%d-04-01" % start_year, "%d-03-31" % (start_year + 1)


def main(inputs, env_variables):
    merchant_id = (inputs.get("merchant_id") or "").strip()
    if not merchant_id:
        return {"output": {"error": "merchant_id is required"}, "captured_variables": {}}
    start, end = (inputs.get("start") or "").strip(), (inputs.get("end") or "").strip()
    if inputs.get("fy"):
        start, end = fy_window(inputs["fy"])

    params = {"merchant_id": merchant_id}
    if start:
        params["start"] = start
    if end:
        params["end"] = end
    data = _api(env_variables, "/ledger/rollup", params)
    merchant = _api(env_variables, "/merchants/%s" % merchant_id)
    mix = _api(env_variables, "/merchant_mix", {"merchant_id": merchant_id})

    buckets = {}
    for row in data["rollup"]:
        b = buckets.setdefault(row["label"], {"attested": 0, "proposed": 0, "count": 0})
        b[row["status"]] = b.get(row["status"], 0) + row["amount"]
        b["count"] += row["n"]

    def total(status):
        return sum(b.get(status, 0) for lab, b in buckets.items() if lab in SUPPLY)

    attested, proposed = total("attested"), total("proposed")
    cov = data["coverage"]
    excluded = [{"label": lab, "amount": b.get("attested", 0) + b.get("proposed", 0),
                 "count": b["count"], "why_excluded": EXCLUDED_BECAUSE.get(lab, "")}
                for lab, b in sorted(buckets.items()) if lab not in SUPPLY]

    workings = [
        "Gross credits in period: Rs %s across %d payments." % (cov["amount"], cov["n"]),
        "Less money that is not a supply: Rs %s." % sum(e["amount"] for e in excluded),
        "Aggregate turnover (attested): Rs %s." % attested,
        "Still unaccounted for: Rs %s across %d payments." % (cov["untagged_amount"], cov["untagged"]),
        "Basis: CGST Act s.2(6) - aggregate turnover is taxable plus exempt supplies.",
    ]
    share = mix.get("exempt_share_of_billed_value")
    if share is not None:
        workings.append(
            "Exempt vs taxable for QR sales with no itemised bill is apportioned from this shop's "
            "POS-billed sales, where %.0f%% of value is exempt. The turnover total does not depend "
            "on that split - only the rate applied to it does." % (share * 100))
    out = {
        "merchant_id": merchant_id,
        "business_name": merchant.get("business_name"),
        "period": {"start": start or "all", "end": end or "all"},
        "gross_credits": cov["amount"],
        "aggregate_turnover_attested": attested,
        "aggregate_turnover_including_provisional": attested + proposed,
        "taxable_supplies": sum(buckets.get("taxable_supply", {}).get(s, 0) for s in ("attested", "proposed")),
        "exempt_supplies": sum(buckets.get("exempt_supply", {}).get(s, 0) for s in ("attested", "proposed")),
        "excluded": excluded,
        "coverage": cov,
        "exempt_taxable_split_basis": ("apportioned from POS-billed sales (%.0f%% exempt by value)"
                                       % (share * 100)) if share is not None else "no billed sales to sample",
        "workings": workings,
        "caveat": "Digital receipts only. Cash sales are not in this ledger and must be added by "
                  "the merchant or their CA before any figure is filed.",
    }
    return {"output": out, "captured_variables": {
        "aggregate_turnover": attested, "gross_credits": cov["amount"],
        "unaccounted_amount": cov["untagged_amount"]}}
