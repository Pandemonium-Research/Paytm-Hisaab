# ENV_VARS: ["HISAAB_API", "HISAAB_KEY"]
"""Phinite custom tool 11 — get_untagged_credits.

The nightly pass's work queue: credits that carry no provenance tag yet. Provenance calls
this first, then works through the rows calling classify_credit_rules on each.

This existed only as a service endpoint until now. `simulate_year` reaches the ledger
through the Store class directly rather than over HTTP, so the nightly pass had never
actually run through the tool layer and the gap went unnoticed.

Dates are IST (+05:30), matching the ledger. `date_to` is inclusive, so a pass run on the
morning of the 10th should use date_to 2026-03-09 to cover everything up to last night.

Inputs
    merchant_id (string, required)
    date_from   (string, optional)  YYYY-MM-DD, inclusive
    date_to     (string, optional)  YYYY-MM-DD, inclusive
    limit       (number, optional)  default 200, hard cap 2000

Env
    HISAAB_API, HISAAB_KEY

Paste the whole file into Dev Studio. Standard library only.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 30
DEFAULT_LIMIT = 200
MAX_LIMIT = 2000


def _get(env, path, params=None):
    base = (env.get("HISAAB_API") or "").rstrip("/")
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"X-Hisaab-Key": env.get("HISAAB_KEY") or ""})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(inputs, env_variables):
    merchant_id = str(inputs.get("merchant_id") or "").strip()
    if not merchant_id:
        return {"output": {"error": "merchant_id is required"}, "captured_variables": {}}

    date_from = str(inputs.get("date_from") or "").strip()
    date_to = str(inputs.get("date_to") or "").strip()
    try:
        limit = int(inputs.get("limit") or DEFAULT_LIMIT)
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    limit = max(1, min(MAX_LIMIT, limit))

    params = {"merchant_id": merchant_id, "limit": limit}
    if date_from:
        params["date_from"] = date_from
    if date_to:
        params["date_to"] = date_to

    try:
        data = _get(env_variables, "/untagged", params)
    except urllib.error.HTTPError as e:
        return {"output": {"error": "HTTP %s reading untagged credits" % e.code},
                "captured_variables": {}}
    except Exception as e:  # noqa: BLE001 - surface to the agent, never kill the pass
        return {"output": {"error": "%s reading untagged credits" % type(e).__name__},
                "captured_variables": {}}

    rows = data.get("rows", [])
    total = data.get("total", len(rows))

    credits = [{
        "txn_id": r["txn_id"],
        "ts": r["ts"],
        "date": r["ts"][:10],
        "time": r["ts"][11:16],
        "amount": r["amount"],
        "channel": r["channel"],
        "counterparty_id": r["counterparty_id"],
        "counterparty_name": r["counterparty_name"],
        "is_billed": bool(r.get("pos_bill_id")),
    } for r in rows]

    out = {
        "merchant_id": merchant_id,
        "period": {"from": date_from or "all", "to": date_to or "all"},
        "total_untagged": total,
        "returned": len(credits),
        "truncated": total > len(credits),
        "credits": credits,
        "next_step": "Call classify_credit_rules on each txn_id. Take the label when it "
                     "returns one; investigate with get_payer_history only when it returns "
                     "null. Then propose_tag for every credit, so none is left untagged.",
    }
    if not credits:
        out["note"] = ("Nothing to classify in this window. Every credit already carries a "
                       "tag, so the pass has no work to do.")

    return {"output": out, "captured_variables": {
        "untagged_count": total,
        "untagged_returned": len(credits),
        "first_untagged_txn_id": credits[0]["txn_id"] if credits else "",
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
