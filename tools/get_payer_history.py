"""Phinite custom tool: get_payer_history.

Everything visible about the payer behind one credit: how often they have paid before,
through which channels, whether the merchant has ever paid *them*, whether the handle is
one of the merchant's own linked accounts, and whether an identical payment sits minutes
away. This is the evidence the Provenance agent reasons over.

Parameters: merchant_id (string, required), txn_id (string, required).
Self-contained: paste this whole file into Dev Studio. Standard library only.
"""
import json
import urllib.parse
import urllib.request


def _api(env, path, params=None, body=None, key="HISAAB_KEY"):
    base = (env.get("HISAAB_API") or "http://127.0.0.1:8000").rstrip("/")
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                 headers={"X-API-Key": env.get(key) or "", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def main(inputs, env_variables):
    merchant_id = (inputs.get("merchant_id") or "").strip()
    txn_id = (inputs.get("txn_id") or "").strip()
    if not merchant_id or not txn_id:
        return {"output": {"error": "merchant_id and txn_id are required"}, "captured_variables": {}}
    h = _api(env_variables, "/payer_history", {"merchant_id": merchant_id, "txn_id": txn_id})

    c, prior = h["credit"], h["prior_credits"]
    cues = []
    if h["is_linked_own_account"]:
        cues.append("payer handle is an account the merchant linked as their own")
    if h["owner_surname_in_payer_name"]:
        cues.append("payer name shares the owner's surname")
    if h["merchant_has_paid_this_payer"]["count"]:
        cues.append("the merchant has paid this counterparty %d times (looks like a supplier)"
                    % h["merchant_has_paid_this_payer"]["count"])
    if h["twin_payments_within_30min"]:
        cues.append("%d identical payment(s) from the same payer within 30 minutes"
                    % len(h["twin_payments_within_30min"]))
    if c.get("refunded_by"):
        cues.append("this credit was refunded")
    if c["channel"] in ("UPI_INTENT", "IMPS", "BANK_TRANSFER"):
        cues.append("paid directly to the VPA/account rather than scanning the shop QR")
    if h["amount_is_round"]:
        cues.append("round amount")
    if h["hour"] >= 21 or h["hour"] < 7:
        cues.append("outside shop hours (%02d:00)" % h["hour"])
    if c.get("note"):
        cues.append('payment note: "%s"' % c["note"])
    if prior["count"] == 0:
        cues.append("first time this payer has paid the merchant")
    elif prior["count"] >= 5:
        cues.append("regular payer: %d prior credits totalling Rs %s" % (prior["count"], prior["total"]))

    h["cues"] = cues
    h["summary"] = "Rs %s at %s from %s. %s" % (
        c["amount"], c["ts"][:16].replace("T", " "), c["counterparty_name"] or c["counterparty_handle"],
        "; ".join(cues) if cues else "no distinguishing signals.")
    return {"output": h, "captured_variables": {"payer_id": h["payer"]["counterparty_id"],
                                                "payer_prior_credits": prior["count"]}}
