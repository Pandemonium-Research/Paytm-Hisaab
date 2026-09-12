# ENV_VARS: ["HISAAB_API", "HISAAB_KEY"]
"""Phinite custom tool 7/13 — compute_aggregate_turnover.

Aggregate turnover under CGST s.2(6) = taxable supplies + exempt supplies. Money that is
not a supply - family transfers, the merchant's own accounts, loans and chit payouts,
duplicates, supplier refunds - is excluded and shown separately, because the argument with
a notice is entirely about that difference.

Attested tags and merely proposed ones are reported apart. A pack may quote the attested
figure; the provisional one is for the merchant's own planning.

Inputs
    merchant_id (string, required)
    fy          (string, optional)  e.g. 2025-26 - sets the window to 1 Apr - 31 Mar
    start, end  (string, optional)  YYYY-MM-DD, if you want a custom window

Env
    HISAAB_API, HISAAB_KEY

Paste the whole file into Dev Studio. Standard library only.
"""
import json
import urllib.error
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
TIMEOUT = 30


def _get(env, path, params=None):
    base = (env.get("HISAAB_API") or "").rstrip("/")
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"X-Hisaab-Key": env.get("HISAAB_KEY") or ""})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fy_window(fy):
    year = int(str(fy).split("-")[0])
    return "%d-04-01" % year, "%d-03-31" % (year + 1)


def main(inputs, env_variables):
    merchant_id = str(inputs.get("merchant_id") or "").strip()
    if not merchant_id:
        return {"output": {"error": "merchant_id is required"}, "captured_variables": {}}
    start = str(inputs.get("start") or "").strip()
    end = str(inputs.get("end") or "").strip()
    if inputs.get("fy"):
        start, end = fy_window(inputs["fy"])

    params = {"merchant_id": merchant_id}
    if start:
        params["date_from"] = start
    if end:
        params["date_to"] = end
    try:
        roll = _get(env_variables, "/ledger/rollup", params)
        merchant = _get(env_variables, "/merchants/" + urllib.parse.quote(merchant_id))
        mix = _get(env_variables, "/merchant_mix", dict(params))
    except urllib.error.HTTPError as e:
        return {"output": {"error": "HTTP %s computing turnover" % e.code}, "captured_variables": {}}

    by_label = roll.get("by_label", {})
    gross = roll.get("gross_credits", {}) or {}
    untagged = roll.get("untagged", {}) or {}

    def amount(label, status):
        return ((by_label.get(label) or {}).get(status) or {}).get("amount", 0)

    def both(label):
        return amount(label, "attested") + amount(label, "proposed")

    attested = sum(amount(l, "attested") for l in SUPPLY)
    provisional = sum(both(l) for l in SUPPLY)

    # Exempt vs taxable: exact where there is a bill, apportioned where there is not.
    # Taking each unbilled sale's majority label instead would push the entire estimate to
    # whichever side the shop mostly sells - and understating taxable turnover is the one
    # error this product cannot afford to make.
    share = mix.get("exempt_share_of_billed_value")
    unbilled = mix.get("unbilled_supply_value") or 0
    if share is not None and unbilled:
        exempt_supplies = mix.get("billed_exempt_value", 0) + int(round(unbilled * share))
        taxable_supplies = max(0, provisional - exempt_supplies)
        split_basis = ("%s billed exactly from item lines; %s of unbilled QR sales apportioned "
                       "at the billed ratio of %.0f%% exempt"
                       % (mix.get("billed_total_value", 0), unbilled, share * 100))
    else:
        exempt_supplies, taxable_supplies = both("exempt_supply"), both("taxable_supply")
        split_basis = "taken from the per-credit labels; no billed sales to apportion from"
    excluded = []
    for label, buckets in sorted(by_label.items()):
        if label in SUPPLY:
            continue
        total = both(label)
        count = sum((buckets.get(s) or {}).get("count", 0) for s in ("attested", "proposed"))
        excluded.append({"label": label, "amount": total, "count": count,
                         "why_excluded": EXCLUDED_BECAUSE.get(label, "")})

    workings = [
        "Gross credits in the period: Rs %s across %d payments."
        % (gross.get("amount", 0), gross.get("count", 0)),
        "Less money that is not a supply: Rs %s." % sum(e["amount"] for e in excluded),
        "Aggregate turnover: Rs %s, of which Rs %s is confirmed by the merchant."
        % (provisional, attested),
        "Still unaccounted for: Rs %s across %d payments."
        % (untagged.get("amount", 0), untagged.get("count", 0)),
        "Basis: CGST Act s.2(6) - aggregate turnover is taxable plus exempt supplies.",
    ]
    if share is not None:
        workings.append(
            "Exempt vs taxable: %s. The turnover total does not depend on that split - only the "
            "rate applied to it does, so it is an estimate and is labelled as one." % split_basis)

    out = {
        "merchant_id": merchant_id,
        "business_name": merchant.get("business_name"),
        "period": {"start": start or "all", "end": end or "all"},
        "gross_credits": gross.get("amount", 0),
        "aggregate_turnover_attested": attested,
        "aggregate_turnover_including_provisional": provisional,
        "taxable_supplies": taxable_supplies,
        "exempt_supplies": exempt_supplies,
        "supplies_by_label_before_apportionment": {"taxable_supply": both("taxable_supply"),
                                                   "exempt_supply": both("exempt_supply")},
        "excluded": excluded,
        "coverage": {"credits": gross.get("count", 0), "untagged": untagged.get("count", 0),
                     "untagged_amount": untagged.get("amount", 0),
                     "attested_amount": attested},
        "exempt_taxable_split_basis": split_basis,
        "workings": workings,
        "caveat": "Digital receipts only. Cash sales are not in this ledger and must be added by "
                  "the merchant or their CA before any figure is filed.",
    }
    return {"output": out, "captured_variables": {
        "aggregate_turnover": provisional, "gross_credits": gross.get("amount", 0),
        "unaccounted_amount": untagged.get("amount", 0)}}


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
