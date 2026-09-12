"""Phinite custom tool: get_attestation_queue.

The daily batch. Returns at most a few credits the merchant should look at, biggest rupees
first, each with the proposal and the reason behind it. PLAN's rule: if this asks about more
than ~3 credits a day, the product is dead - so max_items is capped hard.

Parameters: merchant_id (string, required), day (string YYYY-MM-DD, optional),
max_items (number, default 3).
Self-contained: paste this whole file into Dev Studio. Standard library only.
"""
import json
import urllib.parse
import urllib.request

LABEL_PHRASE = {
    "personal_transfer": "money from family, not a sale",
    "inter_account": "your own money moved between your accounts",
    "non_business": "not business income (loan, chit, gift)",
    "refund_reversal": "money coming back from a supplier",
    "duplicate": "the same sale paid twice",
    "taxable_supply": "a taxable sale",
    "exempt_supply": "an exempt sale",
    "unclassified": "unclear",
}


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
    day = (inputs.get("day") or "").strip()
    try:
        max_items = int(inputs.get("max_items") or 3)
    except (TypeError, ValueError):
        max_items = 3
    if not merchant_id:
        return {"output": {"error": "merchant_id is required"}, "captured_variables": {}}

    params = {"merchant_id": merchant_id, "max_items": max(1, min(3, max_items))}
    if day:
        params["day"] = day
    queue = _api(env_variables, "/attestation_queue", params).get("queue", [])

    items = []
    for q in queue:
        when = q["ts"][:16].replace("T", " ")
        who = q["counterparty_name"] or q["counterparty_handle"]
        items.append({
            "txn_id": q["txn_id"],
            "amount": q["amount"],
            "when": when,
            "payer": who,
            "channel": q["channel"],
            "proposed_label": q["proposed_label"],
            "reason": q["reason"],
            "confidence": q["confidence"],
            "question": "Rs %s on %s from %s - %s?" % (
                q["amount"], when, who, LABEL_PHRASE.get(q["proposed_label"], q["proposed_label"])),
        })
    return {
        "output": {"merchant_id": merchant_id, "day": day or "all pending", "count": len(items),
                   "items": items,
                   "instruction": "Ask these one at a time in the merchant's language. Offer the "
                                  "proposed answer as a yes/no tap, plus the other likely labels. "
                                  "Commit each answer with commit_attestation."},
        "captured_variables": {"queue_size": len(items),
                               "queue_txn_ids": ",".join(i["txn_id"] for i in items)},
    }
