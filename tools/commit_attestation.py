"""Phinite custom tool: commit_attestation.

The only way a tag becomes final. Attach this tool to the Merchant agent node alone, and
deny it everywhere else: a merchant-attested ledger built as the money arrives is the thing
that survives a hearing, and an agent quietly attesting on the merchant's behalf destroys
exactly that property.

It needs HISAAB_ATTEST_KEY, which is set only on the merchant-facing graph, so the storage
layer enforces the same boundary as the tool policy.

Parameters: txn_id (string, required), label (string, required), source (string, default
"merchant"), note (string, optional).
Self-contained: paste this whole file into Dev Studio. Standard library only.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

LABELS = ("taxable_supply", "exempt_supply", "personal_transfer", "refund_reversal",
          "duplicate", "inter_account", "non_business")


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
    source = (inputs.get("source") or "merchant").strip()
    note = (inputs.get("note") or "").strip()
    if not txn_id or label not in LABELS:
        return {"output": {"error": "txn_id required and label must be one of %s" % (LABELS,)},
                "captured_variables": {}}
    try:
        res = _api(env_variables, "/ledger/attest", key="HISAAB_ATTEST_KEY", body={
            "txn_id": txn_id, "label": label, "source": source, "note": note})
    except urllib.error.HTTPError as e:
        if e.code == 403:
            return {"output": {"error": "this agent is not permitted to commit attestations"},
                    "captured_variables": {}}
        raise
    tag = res.get("tag") or {}
    return {
        "output": {"tag": tag, "confirmed": tag.get("status") == "attested",
                   "message": "Recorded: %s. This is now part of your books." % label.replace("_", " ")},
        "captured_variables": {"attested_label": tag.get("label"), "attested_txn_id": txn_id},
    }
