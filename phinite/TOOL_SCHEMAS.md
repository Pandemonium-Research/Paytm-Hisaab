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

---

## 2. `get_payer_history`

**Description**

> Everything the merchant's own records say about whoever sent one payment: how many times
> they have paid before and how much, which channels they use, whether the merchant has ever
> paid *them*, whether the handle is an account the merchant registered as their own, and
> whether an identical payment sits minutes away. Call it before judging any credit.

| Name | Type | Required | Description |
|---|---|---|---|
| `merchant_id` | string | yes | e.g. `MID_DEMO_SAHANA` |
| `txn_id` | string | yes | the credit in question |

Returns `credit`, `prior_credits`, `channels_used`, `merchant_has_paid_this_payer`,
`twin_payments_within_30min`, `is_linked_own_account`, `owner_surname_in_payer_name`, a `cues`
list and a one-line `summary`. **Captured**: `payer_id`, `payer_prior_credits`, `payer_is_own_account`.

**Test**: `DM0012580` → "shares the owner's surname; round amount; regular payer: 39 prior credits".

## 3. `classify_credit_rules`

**Description**

> Apply the deterministic provenance rules to one credit. Returns a label with its evidence
> when the rules settle it, or `label: null` when they do not — that is your cue to reason
> about it yourself. `ask_merchant` says whether it should go into the merchant's daily queue.

| Name | Type | Required | Description |
|---|---|---|---|
| `merchant_id` | string | yes | |
| `txn_id` | string | yes | |

**Captured**: `rule_label`, `rule_confidence`, `rule_ask_merchant`.

**Test**: `DM0013171` → `exempt_supply` 0.95, `ask_merchant: false` (it has a bill).
`DM0012580` → `personal_transfer` 0.55, `ask_merchant: true`.

## 4. `propose_tag`

| Name | Type | Required | Description |
|---|---|---|---|
| `txn_id` | string | yes | |
| `label` | string | yes | one of the seven, or `unclassified` |
| `reason` | string | yes | what the merchant and a CA will read |
| `confidence` | number | yes | 0–1 |
| `ask` | boolean | no | put it in the merchant's queue — pass `ask_merchant` from tool 3 |

Never overwrites an attestation. **Captured**: `proposed_label`, `tag_status`.

## 5. `commit_attestation` — Merchant graph only

| Name | Type | Required | Description |
|---|---|---|---|
| `txn_id` | string | yes | |
| `label` | string | yes | one of the seven; `unclassified` is refused |
| `source` | string | no | default `merchant` |
| `note` | string | no | the merchant's own words |

Sends `HISAAB_ATTEST_KEY`. On `hisaab-watch` it returns "this agent is not permitted to commit
attestations" instead of writing — the boundary fails loudly. **Captured**: `attested_label`,
`attested_txn_id`.

## 6. `get_attestation_queue`

**Description**

> The few credits worth the merchant's attention from the days before `date`, least confident
> first, at most three. Ask them one at a time and commit each answer before moving on.

| Name | Type | Required | Description |
|---|---|---|---|
| `merchant_id` | string | yes | |
| `date` | string | yes | the day you are asking, `YYYY-MM-DD` |
| `lookback_days` | number | no | default 2, so Tuesday's batch covers the weekend |
| `max_items` | number | no | default 3, hard cap 3 |

**Test**: `date` = `2026-03-10`, `lookback_days` = 2 → exactly the three beat-1 credits:
₹15,000 own savings, ₹7,500 spouse, ₹4,850 bulk sale.

## 7. `compute_aggregate_turnover`

| Name | Type | Required | Description |
|---|---|---|---|
| `merchant_id` | string | yes | |
| `fy` | string | no | e.g. `2025-26`, sets 1 Apr – 31 Mar |
| `start`, `end` | string | no | custom window |

Returns turnover attested vs including provisional, the excluded buckets with reasons, coverage,
and `workings` in plain words. **Captured**: `aggregate_turnover`, `gross_credits`, `unaccounted_amount`.

**Test**: `fy` = `2025-26` → ~₹42.2L aggregate against ₹60.98L of gross credits.

## 8. `project_threshold_breach`

| Name | Type | Required | Description |
|---|---|---|---|
| `merchant_id` | string | yes | |
| `as_of` | string | no | project using only data up to this date |
| `fy` | string | no | default `2025-26` |

**Test**: `as_of` = `2026-01-31` → projects ~14–15 Mar, about six weeks of warning. No `as_of` →
already crossed, registration required. A vegetable-only shop returns `exclusively_exempt: true`
and "no registration required" even above ₹40L.

## 9. `isolate_disputed_credit`

| Name | Type | Required | Description |
|---|---|---|---|
| `merchant_id` | string | yes | |
| `utr` | string | no | what a freeze notice carries |
| `amount` | number | no | fallback |
| `date` | string | no | fallback |
| `window_days` | number | no | default 7 |

With no single match it returns the candidates and asks for the UTR rather than guessing.
**Captured**: `disputed_txn_id`, `disputed_utr`, `disputed_amount`, `disputed_date`.

**Test**: `utr` = `608019013171` → `DM0013171`, one of 409 credits that week, with `DM0012998`
listed as the other ₹4,200 payment.

## 10. `build_evidence_pack`

| Name | Type | Required | Description |
|---|---|---|---|
| `merchant_id` | string | yes | |
| `kind` | string | yes | `tax` or `freeze` |
| `reference` | string | no | notice or case reference |
| `turnover` | object | for `tax` | output of tool 7 |
| `threshold` | object | for `tax` | output of tool 8 |
| `disputed` | object | for `freeze` | output of tool 9 |

Composes what the other tools returned and never recomputes a figure, so a pack cannot quietly
disagree with the ledger. Carries its own limits: digital receipts only, how much is
merchant-confirmed, and no assertion that the payer was innocent.
