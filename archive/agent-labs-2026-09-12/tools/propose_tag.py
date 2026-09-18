# ENV_VARS: ["HISAAB_API", "HISAAB_KEY"]
"""Phinite custom tool 4/13 — propose_tag.

Writes a *proposed* provenance tag. The Provenance agent may call this; its tool policy
must deny commit_attestation, so nothing it writes reaches an evidence pack until the
merchant has confirmed it.

`ask` is what puts the credit in front of the merchant. classify_credit_rules decides it:
low confidence, or enough money at stake that a confident guess still isn't good enough.

Inputs
    txn_id     (string, required)
    label      (string, required)  one of the seven labels, or unclassified
    reason     (string, required)  what the merchant and a CA will read
    confidence (number, required)  0-1
    ask        (boolean, optional) surface it in the merchant's daily queue

Env
    HISAAB_API, HISAAB_KEY

Paste the whole file into Dev Studio. Standard library only.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

LABELS = ("taxable_supply", "exempt_supply", "personal_transfer", "refund_reversal",
          "duplicate", "inter_account", "non_business", "unclassified")
TIMEOUT = 20


def _post(env, path, body, key="HISAAB_KEY"):
    base = (env.get("HISAAB_API") or "").rstrip("/")
    req = urllib.request.Request(
        base + path, data=json.dumps(body).encode("utf-8"), method="POST",
        headers={"X-Hisaab-Key": env.get(key) or "", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(inputs, env_variables):
    txn_id = str(inputs.get("txn_id") or "").strip()
    label = str(inputs.get("label") or "").strip()
    reason = str(inputs.get("reason") or "").strip()
    try:
        confidence = float(inputs.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    ask = inputs.get("ask")
    ask = bool(ask) and str(ask).strip().lower() not in ("false", "0", "no", "")

    if not txn_id or label not in LABELS:
        return {"output": {"ok": False, "error": "txn_id required and label must be one of %s"
                                                 % (LABELS,)}, "captured_variables": {}}
    if not reason:
        return {"output": {"ok": False,
                           "error": "a reason is required: it is what the merchant and a CA read"},
                "captured_variables": {}}

    try:
        tag = _post(env_variables, "/ledger/propose", {
            "txn_id": txn_id, "label": label, "reason": reason,
            "confidence": max(0.0, min(1.0, confidence)), "ask": ask})
    except urllib.error.HTTPError as e:
        return {"output": {"ok": False, "error": "HTTP %s proposing %s" % (e.code, txn_id)},
                "captured_variables": {}}

    already_attested = tag.get("status") == "attested"
    return {
        "output": {"ok": True, "tag": tag, "queued_for_merchant": ask and not already_attested,
                   "note": "the merchant has already attested this credit; the proposal was ignored"
                           if already_attested else ""},
        "captured_variables": {"proposed_label": tag.get("label"), "tag_status": tag.get("status")},
    }


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
