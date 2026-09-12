"""Phinite custom tool: isolate_disputed_credit.

A freeze intimation names an amount, a date and usually a UTR. The shop took hundreds of
payments that week. This finds the one credit in question and pulls its sale record.

If only an amount and date are known, it returns every candidate rather than guessing:
naming the wrong payment to the police is worse than saying "it is one of these two".

Parameters: merchant_id (string, required), utr (string, optional), amount (number, optional),
date (YYYY-MM-DD, optional), window_days (number, default 7).
Self-contained: paste this whole file into Dev Studio. Standard library only.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date as _date
from datetime import timedelta


def _api(env, path, params=None, body=None, key="HISAAB_KEY"):
    base = (env.get("HISAAB_API") or "http://127.0.0.1:8000").rstrip("/")
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                 headers={"X-API-Key": env.get(key) or "", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def _sale_record(credit, tag):
    bill = credit.get("bill") or []
    return {
        "txn_id": credit["txn_id"],
        "utr": credit["utr"],
        "when": credit["ts"],
        "amount": credit["amount"],
        "channel": credit["channel"],
        "till": credit["terminal_id"] or "(QR, no till)",
        "payer_name_as_shown": credit["counterparty_name"],
        "payer_handle": credit["counterparty_handle"],
        "itemised_bill": [{"item": l["item"], "hsn": l["hsn"], "amount": l["line_amount"]} for l in bill],
        "bill_total": sum(l["line_amount"] for l in bill) if bill else None,
        "our_provenance_tag": (tag or {}).get("label"),
        "tag_status": (tag or {}).get("status"),
    }


def main(inputs, env_variables):
    merchant_id = (inputs.get("merchant_id") or "").strip()
    utr = (inputs.get("utr") or "").strip()
    amount = inputs.get("amount")
    day = (inputs.get("date") or "").strip()
    try:
        window = int(inputs.get("window_days") or 7)
    except (TypeError, ValueError):
        window = 7
    if not merchant_id:
        return {"output": {"error": "merchant_id is required"}, "captured_variables": {}}

    matched, candidates = None, []
    if utr:
        try:
            c = _api(env_variables, "/credits/by_utr/%s" % utr)
            if c["merchant_id"] == merchant_id:
                matched = c
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise

    if not matched and amount:
        anchor = _date.fromisoformat(day) if day else None
        params = {"merchant_id": merchant_id, "amount": int(amount), "limit": 50}
        if anchor:
            params["start"] = (anchor - timedelta(days=window)).isoformat()
            params["end"] = (anchor + timedelta(days=window)).isoformat()
        candidates = _api(env_variables, "/credits", params)["credits"]
        exact = [c for c in candidates if day and c["ts"][:10] == day]
        if len(exact) == 1:
            matched, candidates = _api(env_variables, "/credits/%s" % exact[0]["txn_id"]), \
                [c for c in candidates if c["txn_id"] != exact[0]["txn_id"]]
        elif len(candidates) == 1:
            matched, candidates = _api(env_variables, "/credits/%s" % candidates[0]["txn_id"]), []

    if not matched:
        return {"output": {
            "matched": None,
            "candidates": candidates,
            "message": "Could not pin down a single credit. %d payment(s) match the amount in that "
                       "window. Ask the bank or the investigating officer for the UTR."
                       % len(candidates)},
            "captured_variables": {"disputed_txn_id": ""}}

    tag = None
    tags = _api(env_variables, "/ledger", {"merchant_id": merchant_id, "limit": 5000})["tags"]
    for t in tags:
        if t["txn_id"] == matched["txn_id"]:
            tag = t
            break

    ts = matched["ts"][:10]
    anchor = _date.fromisoformat(ts)
    week = _api(env_variables, "/credits", {
        "merchant_id": merchant_id, "start": (anchor - timedelta(days=window)).isoformat(),
        "end": anchor.isoformat(), "limit": 1000})["credits"]
    same_amount = [c for c in week if c["amount"] == matched["amount"] and c["txn_id"] != matched["txn_id"]]

    out = {
        "matched": _sale_record(matched, tag),
        "found_by": "UTR" if utr else "amount and date",
        "credits_in_window": len(week),
        "window_days": window,
        "other_payments_of_same_amount_in_window": [
            {"txn_id": c["txn_id"], "ts": c["ts"], "payer": c["counterparty_name"], "utr": c["utr"]}
            for c in same_amount],
        "statement": "Rs %s received at %s. One payment out of %d in the %d days to %s." % (
            matched["amount"], matched["ts"][:16].replace("T", " "), len(week), window, ts),
        "caution": "This identifies the credit and the goods sold against it. It does not establish "
                   "that the payer was legitimate, and must not be presented as proof of that.",
    }
    return {"output": out, "captured_variables": {
        "disputed_txn_id": matched["txn_id"], "disputed_utr": matched["utr"],
        "disputed_amount": matched["amount"], "disputed_date": ts}}
