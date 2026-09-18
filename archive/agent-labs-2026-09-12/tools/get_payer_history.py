# ENV_VARS: ["HISAAB_API", "HISAAB_KEY"]
"""Phinite custom tool 2/13 — get_payer_history.

Everything visible about the payer behind one credit: how often they have paid before,
through which channels, whether the merchant has ever paid *them*, whether the handle is
one the merchant registered as their own, and whether an identical payment sits minutes
away. This is the evidence the Provenance agent reasons over.

Inputs
    merchant_id (string, required)  e.g. MID_DEMO_SAHANA
    txn_id      (string, required)  e.g. DM0012580

Output
    The credit, the payer's record with this merchant, and a plain-language list of the
    cues that argue for or against it being a sale. No label: that is the agent's call.

Env
    HISAAB_API   base URL of the data service
    HISAAB_KEY   read key

Paste the whole file into Dev Studio. Standard library only; imports nothing local.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 20


def _get(env, path, params=None):
    base = (env.get("HISAAB_API") or "").rstrip("/")
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"X-Hisaab-Key": env.get("HISAAB_KEY") or ""})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def context(env, merchant_id, txn_id):
    """Assemble one credit's full picture from the service's separate reads."""
    credit = _get(env, "/credits/" + urllib.parse.quote(txn_id))
    hist = _get(env, "/payer_history", {"merchant_id": merchant_id, "txn_id": txn_id})
    twins = _get(env, "/credits/%s/twins" % urllib.parse.quote(txn_id))
    merchant = _get(env, "/merchants/" + urllib.parse.quote(merchant_id))
    catalog = _get(env, "/hsn")
    exempt_by_item = {(h["item"], h["hsn"]): bool(h["exempt"])
                      for h in (catalog if isinstance(catalog, list) else [])}

    c = dict(credit)
    c["bill"] = [{"item": ln["item"], "hsn": ln["hsn"], "line_amount": ln["line_amount"],
                  "exempt": exempt_by_item.get((ln["item"], ln["hsn"]), False)}
                 for ln in (credit.get("bill_lines") or [])]
    c["refunded_by"] = twins.get("refunds") or []
    owner = (merchant.get("owner_name") or "").split()
    ts = c["ts"]
    return {
        "credit": c,
        "merchant": merchant,
        "payer": {"counterparty_id": c["counterparty_id"], "handle": c["counterparty_handle"],
                  "name": c["counterparty_name"], "known_names": hist.get("names", []),
                  "known_handles": hist.get("handles", [])},
        # credit_count includes this payment; prior means "before this one".
        "prior_credits": {"count": max(0, (hist.get("credit_count") or 0) - 1),
                          "total": hist.get("credit_total") or 0,
                          "first_seen": hist.get("first_seen"), "last_seen": hist.get("last_seen"),
                          "min_amount": hist.get("credit_min"), "max_amount": hist.get("credit_max")},
        "channels_used": sorted((hist.get("channels") or {}).keys()),
        "merchant_has_paid_this_payer": {"count": hist.get("merchant_paid_count") or 0,
                                         "total": hist.get("merchant_paid_total") or 0},
        "twin_payments_within_30min": twins.get("twins") or [],
        "is_linked_own_account": bool(hist.get("handle_is_linked_own_account")),
        "owner_surname_in_payer_name": bool(owner) and owner[-1].upper() in (c["counterparty_name"] or ""),
        "amount_is_round": c["amount"] % 500 == 0,
        "hour": int(ts[11:13]),
        "date": ts[:10],
        "ledger": credit.get("ledger"),
    }


def cues_for(h):
    c = h["credit"]
    prior = h["prior_credits"]
    cues = []
    if h["is_linked_own_account"]:
        cues.append("payer handle is an account the merchant registered as their own")
    if h["owner_surname_in_payer_name"]:
        cues.append("payer name shares the owner's surname")
    if h["merchant_has_paid_this_payer"]["count"]:
        cues.append("the merchant has paid this counterparty %d times, which is how a supplier looks"
                    % h["merchant_has_paid_this_payer"]["count"])
    if h["twin_payments_within_30min"]:
        cues.append("%d identical payment(s) from the same payer within 30 minutes"
                    % len(h["twin_payments_within_30min"]))
    if c.get("refunded_by"):
        cues.append("this credit was refunded")
    if c["channel"] in ("UPI_INTENT", "IMPS", "BANK_TRANSFER"):
        cues.append("paid straight to the VPA or account rather than scanning the shop QR")
    if h["amount_is_round"]:
        cues.append("round amount")
    if h["hour"] >= 21 or h["hour"] < 7:
        cues.append("outside shop hours (%02d:00)" % h["hour"])
    if c.get("note"):
        cues.append('payment note: "%s"' % c["note"])
    if c.get("bill"):
        cues.append("itemised bill attached, so the goods are known")
    if prior["count"] == 0:
        cues.append("first time this payer has paid the merchant")
    elif prior["count"] >= 5:
        cues.append("regular payer: %d prior credits totalling Rs %s" % (prior["count"], prior["total"]))
    return cues


def main(inputs, env_variables):
    merchant_id = str(inputs.get("merchant_id") or "").strip()
    txn_id = str(inputs.get("txn_id") or "").strip()
    if not merchant_id or not txn_id:
        return {"output": {"found": False, "error": "merchant_id and txn_id are both required"},
                "captured_variables": {}}
    try:
        h = context(env_variables, merchant_id, txn_id)
    except urllib.error.HTTPError as e:
        return {"output": {"found": False, "error": "HTTP %s looking up %s" % (e.code, txn_id)},
                "captured_variables": {}}

    c = h["credit"]
    h["cues"] = cues_for(h)
    h["summary"] = "Rs %s at %s from %s. %s" % (
        c["amount"], c["ts"][:16].replace("T", " "), c["counterparty_name"] or c["counterparty_handle"],
        "; ".join(h["cues"]) if h["cues"] else "Nothing distinguishes it from an ordinary sale.")
    h["found"] = True
    return {"output": h, "captured_variables": {
        "payer_id": h["payer"]["counterparty_id"],
        "payer_prior_credits": h["prior_credits"]["count"],
        "payer_is_own_account": h["is_linked_own_account"],
    }}


# The ENV_VARS header above declares what this tool needs; it does NOT restrict what it can
# read. A tool sees every variable set on its environment, declared or not. So the boundary
# rests on the Phinite tool policy, and on HISAAB_ATTEST_KEY being scoped to hisaab-merchant
# so it is never within reach of a Provenance tool in the first place.
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
