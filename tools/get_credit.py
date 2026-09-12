"""Phinite custom tool 1/13 — get_credit.

Paste the whole file into Dev Studio. It is deliberately self-contained and uses
only the standard library: each tool is published on its own, so nothing here may
import from another tool or from `service/`, and `requests` may not exist in the
sandbox.

Inputs
    txn_id  (string, optional)  e.g. DM0012559
    utr     (string, optional)  12-digit RRN, e.g. 608019013171
    One of the two is required. utr is what a freeze notice actually gives you.

Output
    The credit, its POS bill lines if it was billed, and its current ledger
    standing. No judgment: labelling is the Provenance agent's job.

Env
    HISAAB_API   base URL of the data service
    HISAAB_KEY   read key
"""
import json
import urllib.error
import urllib.parse
import urllib.request

TIMEOUT = 20


def _get(base, path, key, params=None):
    url = base.rstrip("/") + path
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"X-Hisaab-Key": key or ""})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:300]
        return None, f"HTTP {e.code} from {path}: {detail}"
    except Exception as e:  # noqa: BLE001 - surface to the agent, never crash the run
        return None, f"{type(e).__name__} calling {path}: {e}"


def main(inputs, env_variables):
    base = env_variables.get("HISAAB_API", "")
    key = env_variables.get("HISAAB_KEY", "")
    if not base:
        return {
            "output": {"found": False, "error": "HISAAB_API is not set"},
            "captured_variables": {},
        }

    txn_id = str(inputs.get("txn_id") or "").strip()
    utr = str(inputs.get("utr") or "").strip()
    if not txn_id and not utr:
        return {
            "output": {"found": False, "error": "pass either txn_id or utr"},
            "captured_variables": {},
        }

    if txn_id:
        row, err = _get(base, "/credits/" + urllib.parse.quote(txn_id), key)
    else:
        row, err = _get(base, "/credits/by_utr/" + urllib.parse.quote(utr), key)

    if err:
        lookup = txn_id or utr
        return {
            "output": {"found": False, "lookup": lookup, "error": err},
            "captured_variables": {},
        }

    lines = row.get("bill_lines") or []
    ledger = row.get("ledger") or {}

    credit = {
        "txn_id": row["txn_id"],
        "merchant_id": row["merchant_id"],
        "ts": row["ts"],
        "date": row["ts"][:10],
        "time": row["ts"][11:16],
        "direction": row["direction"],
        "amount": row["amount"],
        "channel": row["channel"],
        "counterparty_id": row["counterparty_id"],
        "counterparty_name": row["counterparty_name"],
        "counterparty_handle": row["counterparty_handle"],
        "terminal_id": row["terminal_id"],
        "utr": row["utr"],
        "note": row["note"],
        "orig_txn_id": row["orig_txn_id"],
    }

    # A POS bill is the difference between "a ₹4,200 credit" and "a sale of
    # 12kg onions at 19:47" — which is the whole of demo beat 4.
    bill = {
        "pos_bill_id": row.get("pos_bill_id") or None,
        "billed": bool(lines),
        "line_count": len(lines),
        "lines": [
            {
                "line_no": ln["line_no"],
                "item": ln["item"],
                "hsn": ln["hsn"],
                "line_amount": ln["line_amount"],
            }
            for ln in lines
        ],
        "lines_total": sum(ln["line_amount"] for ln in lines),
    }

    output = {
        "found": True,
        "credit": credit,
        "bill": bill,
        "ledger_status": ledger.get("status", "untagged"),
        "ledger_label": ledger.get("label"),
        "ledger_reason": ledger.get("reason"),
    }

    return {
        "output": output,
        "captured_variables": {
            "txn_id": credit["txn_id"],
            "merchant_id": credit["merchant_id"],
            "amount": credit["amount"],
            "credit_ts": credit["ts"],
            "counterparty_id": credit["counterparty_id"],
            "counterparty_name": credit["counterparty_name"],
            "is_billed": bill["billed"],
            "ledger_status": output["ledger_status"],
        },
    }
