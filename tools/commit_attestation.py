"""Phinite custom tool 5/13 — commit_attestation.

The only way a tag becomes final. Attach this tool to the Merchant agent node alone and
deny it everywhere else: a merchant-attested ledger built as the money arrives is what
survives a hearing, and an agent quietly attesting on the merchant's behalf destroys
exactly that property.

It sends HISAAB_ATTEST_KEY, which is set only on hisaab-merchant, so the service refuses
the call with 403 even if a tool policy is mis-scoped. Two locks, one door.

Inputs
    txn_id (string, required)
    label  (string, required)  one of the seven real labels - never "unclassified"
    source (string, optional)  default "merchant"
    note   (string, optional)  the merchant's own words

Env
    HISAAB_API, HISAAB_ATTEST_KEY

Paste the whole file into Dev Studio. Standard library only.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

LABELS = ("taxable_supply", "exempt_supply", "personal_transfer", "refund_reversal",
          "duplicate", "inter_account", "non_business")
SPOKEN = {
    "taxable_supply": "a taxable sale",
    "exempt_supply": "an exempt sale",
    "personal_transfer": "family money, not a sale",
    "inter_account": "your own money moved between your accounts",
    "non_business": "not business income",
    "refund_reversal": "money returned by a supplier",
    "duplicate": "a double payment",
}
TIMEOUT = 20


def main(inputs, env_variables):
    txn_id = str(inputs.get("txn_id") or "").strip()
    label = str(inputs.get("label") or "").strip()
    source = str(inputs.get("source") or "merchant").strip()
    note = str(inputs.get("note") or "").strip()
    if not txn_id or label not in LABELS:
        return {"output": {"ok": False, "error": "txn_id required and label must be one of %s"
                                                 % (LABELS,)}, "captured_variables": {}}

    base = (env_variables.get("HISAAB_API") or "").rstrip("/")
    body = json.dumps({"txn_id": txn_id, "label": label, "source": source, "note": note}).encode("utf-8")
    req = urllib.request.Request(
        base + "/ledger/attest", data=body, method="POST",
        headers={"X-Hisaab-Key": env_variables.get("HISAAB_ATTEST_KEY") or "",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            tag = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 403:
            return {"output": {"ok": False, "error": "this agent is not permitted to commit "
                                                     "attestations; only the merchant graph is"},
                    "captured_variables": {}}
        return {"output": {"ok": False, "error": "HTTP %s attesting %s" % (e.code, txn_id)},
                "captured_variables": {}}

    return {
        "output": {"ok": True, "tag": tag, "confirmed": tag.get("status") == "attested",
                   "message": "Recorded: %s. This is part of your books now."
                              % SPOKEN.get(label, label.replace("_", " "))},
        "captured_variables": {"attested_label": tag.get("label"), "attested_txn_id": txn_id},
    }
