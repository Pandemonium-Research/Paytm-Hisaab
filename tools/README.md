# Phinite tools

One file per tool. Paste the **whole file** into Dev Studio — each is self-contained and uses
only the Python standard library, so nothing depends on the sandbox having `requests`.

Every handler is `main(inputs, env_variables)` returning `{"output": ..., "captured_variables": ...}`.

## Environment variables (set per environment in Phinite)

| Variable | Value |
|---|---|
| `HISAAB_API` | data service base URL (Render) |
| `HISAAB_KEY` | read + propose key |
| `HISAAB_ATTEST_KEY` | commit key — **only** on the merchant-facing graph |

## Parameters to declare in Dev Studio

| Tool | Parameters | Give it to |
|---|---|---|
| `get_credit` | `txn_id` (string), `utr` (string) — pass one | any |
| `get_payer_history` | `merchant_id` (string, required), `txn_id` (string, required) | Provenance |
| `classify_credit_rules` | `merchant_id` (string, required), `txn_id` (string, required) | Provenance |
| `propose_tag` | `txn_id` (string, required), `label` (string, required), `reason` (string, required), `confidence` (number), `ask` (boolean) | Provenance |
| `commit_attestation` | `txn_id` (string, required), `label` (string, required), `source` (string), `note` (string) | **Merchant only** |
| `get_attestation_queue` | `merchant_id` (string, required), `day` (string YYYY-MM-DD), `max_items` (number, ≤3) | Merchant |
| `compute_aggregate_turnover` | `merchant_id` (string, required), `fy` (string e.g. `2025-26`), `start`, `end` | Evidence |
| `project_threshold_breach` | `merchant_id` (string, required), `as_of` (string YYYY-MM-DD), `fy` (string) | Evidence |
| `isolate_disputed_credit` | `merchant_id` (string, required), `utr` (string), `amount` (number), `date` (string), `window_days` (number) | Evidence |
| `build_evidence_pack` | `merchant_id` (string, required), `kind` (`tax`\|`freeze`, required), `reference` (string), `turnover` (object), `threshold` (object), `disputed` (object) | Evidence |

`build_evidence_pack` composes what the other tools returned — pass their outputs straight in.
It never recomputes a figure, so a pack can't quietly disagree with the ledger.

## How the classifier decides to ask

`classify_credit_rules` returns `ask_merchant`. It is not just low confidence:

- below **₹500**, never ask — a tap costs the merchant more than the error does
- **no label**, or confidence below **0.75** → ask
- a **non-sale** credit of **₹10,000+** → ask even when the rules are sure, because holding a big credit out of turnover is the merchant's call
- a **sale of ₹3,000+** from someone with ≤3 prior payments and no itemised bill → ask, since that is what a notice or a freeze turns on

On the demo merchant that comes to **189 questions across a year, a median of 1.3 a day**, inside
PLAN's ≤3/day budget.

The exempt-vs-taxable split on a QR sale with no bill is *never* asked: it isn't identifiable per
credit. It is apportioned from the shop's POS-billed sales and flagged as an estimate.

## Local harnesses (not Phinite tools)

```
python -m uvicorn service.app:app --port 8000   # terminal 1
python -m tools.simulate_year --reset           # a year of nightly passes + merchant answers
python -m tools.check_beats                     # all four demo beats, against the answer key
python -m tools.run_local                       # one pass through the attestation flow
```

`simulate_year` and `check_beats` read `data/<split>/hidden/` to play the merchant and to check
answers. They are test harnesses. Nothing under `service/` or `tools/` reads `hidden/` at runtime.

`simulate_year` leaves 8–9 Mar 2026 un-attested on purpose, so beat 1 can happen live on stage.
