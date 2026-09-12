# Tool parameter schemas for Dev Studio

Handler code lives in `tools/<name>.py`. Paste the whole file; set the parameters below.

Every handler is self-contained and standard-library only. None of them import from
another tool or from `service/` — Phinite publishes each tool in isolation, and
`requests` may not exist in the sandbox.

## Env variables (Settings -> Environment variables, per environment)

| Name | Value | Set on |
|---|---|---|
| `HISAAB_API` | data service base URL, no trailing slash | both graphs |
| `HISAAB_KEY` | read + propose key | both graphs |
| `HISAAB_ATTEST_KEY` | commit key | **`hisaab-merchant` only** |

Setting `HISAAB_ATTEST_KEY` on `hisaab-watch` would defeat the permission boundary the
whole pitch rests on. The service rejects an attestation carrying the read key with 403,
so a mistake here fails loudly rather than silently.

---

## 1. `get_credit`

Fetch one credit by transaction id or UTR, with its POS bill lines and ledger standing.

**Description** (what the agent sees when deciding to call it):

> Look up a single payment by its transaction id or its 12-digit UTR. Returns the amount,
> timestamp, channel, who paid, the itemised POS bill if the sale was billed, and whether
> the payment already carries a provenance tag. Use it when the merchant asks about a
> specific payment, or when a freeze notice gives you a UTR and you need the sale behind it.

**Parameters**

| Name | Type | Required | Description |
|---|---|---|---|
| `txn_id` | string | no | Transaction id, e.g. `DM0012559`. |
| `utr` | string | no | 12-digit UTR / RRN, e.g. `608019013171`. This is what a freeze notice gives you. |

One of the two is required; the tool returns `found: false` with an error message if neither
is supplied, rather than raising.

**Output shape**

```json
{
  "found": true,
  "credit": {
    "txn_id": "DM0013171", "merchant_id": "MID_DEMO_SAHANA",
    "ts": "2026-03-21T19:47:05+05:30", "date": "2026-03-21", "time": "19:47",
    "direction": "CR", "amount": 4200, "channel": "UPI_POS",
    "counterparty_id": "P4699086598", "counterparty_name": "SUNITHA MURTHY",
    "counterparty_handle": "sunitha.murthy17@okhdfcbank",
    "terminal_id": "POS01", "utr": "608019013171", "note": "", "orig_txn_id": ""
  },
  "bill": {
    "pos_bill_id": "BDM0004334", "billed": true, "line_count": 4,
    "lines": [{"line_no": 1, "item": "Onion", "hsn": "0703", "line_amount": 723}],
    "lines_total": 4200
  },
  "ledger_status": "untagged",
  "ledger_label": null,
  "ledger_reason": null
}
```

**Captured variables**: `txn_id`, `merchant_id`, `amount`, `credit_ts`, `counterparty_id`,
`counterparty_name`, `is_billed`, `ledger_status`.

**Test values in Dev Studio** (demo split):

| Input | Expect |
|---|---|
| `txn_id` = `DM0012559` | ₹15,000, 2026-03-08 23:04, SAHANA GOWDA, `billed: false` |
| `utr` = `608019013171` | ₹4,200, 2026-03-21 19:47, SUNITHA MURTHY, `billed: true`, 4 bill lines |
| `txn_id` = `NOPE` | `found: false`, HTTP 404 in the error string |

The third case matters as much as the first two: the agent has to be able to say "no such
payment" without inventing one.
