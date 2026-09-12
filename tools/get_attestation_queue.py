# ENV_VARS: ["HISAAB_API", "HISAAB_KEY"]
"""Phinite custom tool 6/13 — get_attestation_queue.

The daily batch. Returns the few credits worth the merchant's attention from the days
before `date`, each with the proposal and the reason behind it, least confident first.

PLAN's rule: if this asks about more than ~3 credits a day, the product is dead. The cap
is enforced here and again in the service.

Inputs
    merchant_id   (string, required)
    date          (string, required)  the day the agent is asking, YYYY-MM-DD
    lookback_days (number, optional)  default 2 - Tuesday's batch covers the weekend
    max_items     (number, optional)  default 3, hard cap 3

Env
    HISAAB_API, HISAAB_KEY

Paste the whole file into Dev Studio. Standard library only.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

LABEL_PHRASE = {
    "personal_transfer": "money from family, not a sale",
    "inter_account": "your own money moving between your accounts",
    "non_business": "not business income - a loan, chit payout or gift",
    "refund_reversal": "money coming back from a supplier",
    "duplicate": "the same sale paid twice",
    "taxable_supply": "a taxable sale",
    "exempt_supply": "an exempt sale",
    "unclassified": "something we could not place",
}
TIMEOUT = 20


def _get(env, path, params=None):
    base = (env.get("HISAAB_API") or "").rstrip("/")
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"X-Hisaab-Key": env.get("HISAAB_KEY") or ""})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(inputs, env_variables):
    merchant_id = str(inputs.get("merchant_id") or "").strip()
    day = str(inputs.get("date") or "").strip()
    try:
        lookback = int(inputs.get("lookback_days") or 2)
    except (TypeError, ValueError):
        lookback = 2
    try:
        max_items = int(inputs.get("max_items") or 3)
    except (TypeError, ValueError):
        max_items = 3
    if not merchant_id or not day:
        return {"output": {"error": "merchant_id and date are required"}, "captured_variables": {}}

    try:
        data = _get(env_variables, "/attestation_queue", {
            "merchant_id": merchant_id, "date": day,
            "lookback_days": max(1, min(14, lookback)), "max": max(1, min(3, max_items))})
    except urllib.error.HTTPError as e:
        return {"output": {"error": "HTTP %s reading the queue" % e.code}, "captured_variables": {}}

    items = []
    for row in data.get("rows", []):
        proposal = row.get("proposal") or {}
        when = row["ts"][:16].replace("T", " ")
        who = row["counterparty_name"] or row["counterparty_handle"]
        items.append({
            "txn_id": row["txn_id"],
            "amount": row["amount"],
            "when": when,
            "payer": who,
            "channel": row["channel"],
            "note": row.get("note", ""),
            "billed": bool(row.get("bill_lines")),
            "proposed_label": proposal.get("label"),
            "reason": proposal.get("reason"),
            "confidence": proposal.get("confidence"),
            "question": "Rs %s on %s from %s - %s?" % (
                row["amount"], when, who,
                LABEL_PHRASE.get(proposal.get("label"), "what was this")),
        })

    return {
        "output": {
            "merchant_id": merchant_id,
            "asked_on": data.get("asked_on", day),
            "covering": "%s to %s" % (data.get("window_from"), data.get("window_to")),
            "count": len(items),
            "pending_total": data.get("pending_total", len(items)),
            "items": items,
            "instruction": "Ask these one at a time, in the merchant's language, shortest first. "
                           "Offer the proposed answer as a yes/no tap plus the other likely labels, "
                           "and commit each answer with commit_attestation before moving on. If the "
                           "merchant is unsure, leave it pending rather than guessing for them.",
        },
        "captured_variables": {"queue_size": len(items),
                               "queue_txn_ids": ",".join(i["txn_id"] for i in items)},
    }


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
