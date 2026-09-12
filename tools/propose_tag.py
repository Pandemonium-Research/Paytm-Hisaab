"""Phinite custom tool: propose_tag.

Writes a *proposed* provenance tag. The Provenance agent may call this; its tool policy
must deny commit_attestation, so nothing it writes can reach an evidence pack until the
merchant confirms it.

Parameters: txn_id (string, required), label (string, required), reason (string, required),
confidence (number 0-1, required), ask (boolean, default false - put it in front of the
merchant, which classify_credit_rules decides via ask_merchant).
Self-contained: paste this whole file into Dev Studio. Standard library only.
"""
import json
import urllib.parse
import urllib.request

LABELS = ("taxable_supply", "exempt_supply", "personal_transfer", "refund_reversal",
          "duplicate", "inter_account", "non_business", "unclassified")


def _api(env, path, params=None, body=None, key="HISAAB_KEY"):
    base = (env.get("HISAAB_API") or "http://127.0.0.1:8000").rstrip("/")
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                 headers={"X-API-Key": env.get(key) or "", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def main(inputs, env_variables):
    txn_id = (inputs.get("txn_id") or "").strip()
    label = (inputs.get("label") or "").strip()
    reason = (inputs.get("reason") or "").strip()
    try:
        confidence = float(inputs.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    if not txn_id or label not in LABELS:
        return {"output": {"error": "txn_id required and label must be one of %s" % (LABELS,)},
                "captured_variables": {}}
    if not reason:
        return {"output": {"error": "a reason is required: it is what the merchant and a CA read"},
                "captured_variables": {}}

    ask = inputs.get("ask")
    ask = bool(ask) and str(ask).lower() not in ("false", "0", "no")
    res = _api(env_variables, "/ledger/propose", body={
        "txn_id": txn_id, "label": label, "reason": reason,
        "confidence": max(0.0, min(1.0, confidence)), "ask": ask})
    tag = res.get("tag") or {}
    return {
        "output": {"tag": tag, "note": res.get("note", ""),
                   "awaiting_attestation": tag.get("status") == "proposed"},
        "captured_variables": {"proposed_label": tag.get("label"), "tag_status": tag.get("status")},
    }
