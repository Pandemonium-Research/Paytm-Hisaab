# Phinite tools

One file per tool. Paste the **whole file** into Dev Studio — each is self-contained and uses
only the Python standard library, so nothing depends on the sandbox having `requests`, and no
tool imports another or anything under `service/`.

Every handler is `main(inputs, env_variables)` returning `{"output": ..., "captured_variables": ...}`.

**Parameter schemas, descriptions and test values for Dev Studio live in
[../phinite/TOOL_SCHEMAS.md](../phinite/TOOL_SCHEMAS.md).** This file covers how to run them locally
and why the classifier asks what it asks.

## Environment variables

| Variable | Value | Set on |
|---|---|---|
| `HISAAB_API` | data service base URL, no trailing slash | both graphs |
| `HISAAB_KEY` | read + propose key | both graphs |
| `HISAAB_ATTEST_KEY` | commit key | `hisaab-merchant` only |

Requests send the key as `X-Hisaab-Key`.

## The tools

| # | Tool | Used by |
|---|---|---|
| 1 | `get_credit` | any |
| 2 | `get_payer_history` | Provenance |
| 3 | `classify_credit_rules` | Provenance |
| 4 | `propose_tag` | Provenance |
| 5 | `commit_attestation` | **Merchant only** |
| 6 | `get_attestation_queue` | Merchant |
| 7 | `compute_aggregate_turnover` | Evidence |
| 8 | `project_threshold_breach` | Evidence |
| 9 | `isolate_disputed_credit` | Evidence |
| 10 | `build_evidence_pack` | Evidence |

Still to write: `map_hsn_exemption`, `detect_return_mismatch`, `draft_ncrp_grievance` (all P1).

## How the classifier decides to ask

`classify_credit_rules` returns `ask_merchant`, and it is not just low confidence:

- below **₹500**, never ask — a tap costs the merchant more than the error does
- **no label**, or confidence below **0.75** → ask
- a **non-sale** credit of **₹10,000+** → ask even when the rules are sure, because holding a big
  credit out of turnover is the merchant's call, not ours
- a **sale of ₹3,000+** from someone with ≤3 prior payments and no itemised bill → ask, since an
  unusually large payment from a near-stranger is what a notice or a freeze turns on

On the demo merchant that comes to **189 questions across a year, a median of 1.3 a day**, none
over PLAN's ≤3/day budget.

The exempt-vs-taxable split on a QR sale with no bill is *never* asked: it is not identifiable per
credit. It is apportioned from the shop's POS-billed sales and flagged as an estimate, and the
turnover total does not depend on it — only the rate applied to it does.

## Local harnesses (not Phinite tools)

```
python -m uvicorn service.app:app --port 8000   # terminal 1
python -m tools.simulate_year --reset           # a year of nightly passes + merchant answers
python -m tools.check_beats                     # all four demo beats, against the answer key
python -m tools.run_local                       # one pass through the attestation flow (dry)
python -m tools.run_local --commit              # ... and actually attest the first item
```

`simulate_year` and `check_beats` read `data/<split>/hidden/` to play the merchant and to mark the
paper. They are test harnesses; nothing under `service/` or the published tools reads `hidden/`.

`simulate_year` leaves 8–9 Mar 2026 un-attested on purpose, so beat 1 happens live on stage. Re-run
it with `--reset` after any `run_local --commit`, or the queue the demo needs will be short.
