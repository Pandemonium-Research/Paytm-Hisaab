# ENV_VARS: ["HISAAB_API", "HISAAB_KEY"]
"""Phinite custom tool 9/13 — isolate_disputed_credit.

A freeze intimation names an amount, a date and usually a UTR. The shop took hundreds of
payments that week. This finds the one credit in question and pulls its sale record.

If only an amount and date are known it returns every candidate rather than guessing:
naming the wrong payment to the police is worse than saying "it is one of these two".

Inputs
    merchant_id (string, required)
    utr         (string, optional)  what a freeze notice usually carries
    amount      (number, optional)  fallback when there is no UTR
    date        (string, optional)  YYYY-MM-DD
    window_days (number, optional)  default 7

Env
    HISAAB_API, HISAAB_KEY

Paste the whole file into Dev Studio. Standard library only.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date as _date
from datetime import timedelta

TIMEOUT = 30


def _get(env, path, params=None):
    base = (env.get("HISAAB_API") or "").rstrip("/")
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"X-Hisaab-Key": env.get("HISAAB_KEY") or ""})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _sale_record(credit):
    lines = credit.get("bill_lines") or []
    ledger = credit.get("ledger") or {}
    return {
        "txn_id": credit["txn_id"],
        "utr": credit["utr"],
        "when": credit["ts"],
        "amount": credit["amount"],
        "channel": credit["channel"],
        "till": credit["terminal_id"] or "(QR, no till)",
        "payer_name_as_shown": credit["counterparty_name"],
        "payer_handle": credit["counterparty_handle"],
        "itemised_bill": [{"item": l["item"], "hsn": l["hsn"], "amount": l["line_amount"]}
                          for l in lines],
        "bill_total": sum(l["line_amount"] for l in lines) if lines else None,
        "our_provenance_tag": ledger.get("label"),
        "tag_status": ledger.get("status", "untagged"),
    }


def main(inputs, env_variables):
    merchant_id = str(inputs.get("merchant_id") or "").strip()
    utr = str(inputs.get("utr") or "").strip()
    amount = inputs.get("amount")
    day = str(inputs.get("date") or "").strip()
    try:
        window = int(inputs.get("window_days") or 7)
    except (TypeError, ValueError):
        window = 7
    if not merchant_id:
        return {"output": {"error": "merchant_id is required"}, "captured_variables": {}}

    matched, candidates = None, []
    if utr:
        try:
            c = _get(env_variables, "/credits/by_utr/" + urllib.parse.quote(utr))
            if c.get("merchant_id") == merchant_id:
                matched = c
        except urllib.error.HTTPError as e:
            if e.code != 404:
                return {"output": {"error": "HTTP %s looking up UTR" % e.code},
                        "captured_variables": {}}

    if not matched and amount:
        params = {"merchant_id": merchant_id, "min_amount": int(amount),
                  "max_amount": int(amount), "limit": 50}
        if day:
            anchor = _date.fromisoformat(day)
            params["date_from"] = (anchor - timedelta(days=window)).isoformat()
            params["date_to"] = (anchor + timedelta(days=window)).isoformat()
        candidates = _get(env_variables, "/credits", params).get("rows", [])
        same_day = [c for c in candidates if day and c["ts"][:10] == day]
        pick = same_day[0] if len(same_day) == 1 else (candidates[0] if len(candidates) == 1 else None)
        if pick:
            matched = _get(env_variables, "/credits/" + urllib.parse.quote(pick["txn_id"]))
            candidates = [c for c in candidates if c["txn_id"] != pick["txn_id"]]

    if not matched:
        return {"output": {
            "matched": None,
            "candidates": [{"txn_id": c["txn_id"], "ts": c["ts"], "amount": c["amount"],
                            "payer": c["counterparty_name"], "utr": c["utr"]} for c in candidates],
            "message": "Could not pin this down to one credit. %d payment(s) match the amount in "
                       "that window. Ask the bank or the investigating officer for the UTR."
                       % len(candidates)},
            "captured_variables": {"disputed_txn_id": ""}}

    anchor = _date.fromisoformat(matched["ts"][:10])
    week = _get(env_variables, "/credits", {
        "merchant_id": merchant_id, "date_from": (anchor - timedelta(days=window)).isoformat(),
        "date_to": anchor.isoformat(), "limit": 1000})
    same_amount = [c for c in week.get("rows", [])
                   if c["amount"] == matched["amount"] and c["txn_id"] != matched["txn_id"]]

    out = {
        "matched": _sale_record(matched),
        "found_by": "UTR" if utr else "amount and date",
        "credits_in_window": week.get("total", len(week.get("rows", []))),
        "window_days": window,
        "other_payments_of_same_amount_in_window": [
            {"txn_id": c["txn_id"], "ts": c["ts"], "payer": c["counterparty_name"], "utr": c["utr"]}
            for c in same_amount],
        "statement": "Rs %s received at %s. One payment out of %d in the %d days to %s." % (
            matched["amount"], matched["ts"][:16].replace("T", " "),
            week.get("total", 0), window, anchor.isoformat()),
        "caution": "This identifies the credit and the goods sold against it. It does not establish "
                   "that the payer was legitimate, and must not be presented as proof of that.",
    }
    return {"output": out, "captured_variables": {
        "disputed_txn_id": matched["txn_id"], "disputed_utr": matched["utr"],
        "disputed_amount": matched["amount"], "disputed_date": matched["ts"][:10]}}


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
