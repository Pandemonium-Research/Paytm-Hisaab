# BUILD_PLAN.md — hackathon day

Companion to [PLAN.md](PLAN.md) (what we're building and why) and [DATA.md](DATA.md) (the data).
This file is the running order, who does what, and the contract between the two tracks.

## Decisions (locked)

| Decision | Choice | Why |
|---|---|---|
| Channel | **Web Chat** | No Meta/BSP credentials or webhook verification. Revisit WhatsApp only if credentials are in hand by midday. |
| Data service host | **Render** | Public HTTPS that survives a laptop sleeping. ngrok tunnel is the backup. |
| Demo data | **Synthetic** (`data/demo`) | Calibrated to the four beats. Show a Paytm sandbox read separately, as proof it connects. |

## Platform shape

Two Agent Graphs, not four separate agents:

- **`hisaab-merchant`** (Conversational, Web Chat) — attestation, alerts, explanation. Master Agent = Merchant; Child Agent = Escalation.
- **`hisaab-watch`** (Autonomous, Cron + API trigger) — nightly provenance pass, threshold watch, evidence packs. Master Agent = Provenance; Child Agent = Evidence.

PLAN's four agents become agent nodes across these two graphs. PLAN's permission boundaries become **tool policies** bound to a single agent node.

Only the Merchant Agent is conversational: beat 1 is a real multi-turn dialogue with a person
present, deploying to a channel. Provenance, Evidence and Escalation have nobody waiting at the
other end — nightly pass and threshold watch on Cron, freeze response and notice pack on API
trigger.

**How the two graphs hand off.** The autonomous pass writes its queue of ambiguous credits to the
data service; the conversational graph reads it with `get_attestation_queue` when the merchant
opens the chat. Deliberately *not* a direct graph-to-graph call — the queue outliving either run is
what makes the handoff demo-safe. Two alternatives, both deferred: a WhatsApp template message that
starts the conversation (needs credentials we decided against), and exposing Evidence as an A2A
Agent Card (the production shape, and the better registry story — wire it only if the identity
pitch needs it).

**API triggers are synchronous with a ~120–150s cap.** Pack assembly for beat 4 can exceed that.
Fire the freeze response as a background task and poll for status; do not put `build_evidence_pack`
on the synchronous path.

## Tracks

- **Track A — Phinite (teammate).** Workspace, graphs, publishing tools, policies, channel, builds, registry, observability, demo rehearsal.
- **Track B — Python (Claude).** Data service, tool handlers, classifier rules and prompts, evaluation numbers.

**Sync points:** (1) tool contract agreed — below; (2) data service URL live; (3) each tool handler published as it lands.

## Running order

| Phase | Track A (Phinite) | Track B (Python) | Time |
|---|---|---|---|
| 0 | Kill-condition checks on the Paytm sandbox; workspace + roles | Agree tool contract; freeze demo data | 30 min |
| 1 | Graph skeletons; publish a hello-world tool; deploy Web Chat to DEV | Data service live on Render; hand over base URL + keys | 1 hr |
| 2 | Publish tools; build Provenance graph; write tool policies | Tool handlers: payer history, rules classifier, turnover, threshold | 2 hrs |
| 3 | Merchant conversation: daily batch, ≤3 questions, one tap, Kannada | Evidence packs (tax + freeze), NCRP draft, eval run for the pitch number | 2 hrs |
| 4 | Human-approval policy on pack delivery; Agent Cards in the registry | Support + fix whatever Phase 4 surfaces | 1 hr |
| 5 | DEV → UAT → PROD promotion; observability walk-through | Phinite Evaluations dataset from the eval split | 1 hr |
| 6 | Rehearse four beats, static fallbacks, slides | Same | 1.5 hrs |

**Phase 1 matters most.** Getting one trivial tool published and answering in Web Chat proves the whole pipeline before any real logic depends on it.

## The tool contract

Every Phinite custom tool is Python with this shape:

```python
def main(inputs, env_variables):
    return {"output": {...}, "captured_variables": {...}}
```

Track B writes each handler in `tools/<tool_name>.py` with exactly that signature, tested locally. Track A pastes it into Dev Studio, sets the parameter schema, tests, publishes.

Shared env variables (set per environment in Phinite):

- `HISAAB_API` — data service base URL
- `HISAAB_KEY` — read + propose key
- `HISAAB_ATTEST_KEY` — commit key, only set on the graph that needs it

### Tools, in build order

| # | Tool | Inputs | Output | Used by | Priority |
|---|---|---|---|---|---|
| 1 | `get_credit` | `txn_id` or `utr` | credit row + POS bill lines | all | P0 |
| 2 | `get_payer_history` | `merchant_id`, `txn_id` | payer stats, first/last seen, channels, twin payments, "merchant has paid them" flag | Provenance | P0 |
| 3 | `classify_credit_rules` | `txn_id` | deterministic label or `null`, with evidence | Provenance | P0 |
| 4 | `propose_tag` | `txn_id`, `label`, `reason`, `confidence` | ledger row (status `proposed`) | Provenance | P0 |
| 5 | `commit_attestation` | `txn_id`, `label`, `source`, `note` | ledger row (status `attested`) | Merchant only | P0 |
| 6 | `get_attestation_queue` | `merchant_id`, `date`, `max=3` | ≤3 ambiguous credits with proposal and reason | Merchant | P0 |
| 7 | `compute_aggregate_turnover` | `merchant_id`, `fy`, `as_of?` | taxable + exempt total, excluded buckets, workings | Evidence | P0 |
| 8 | `project_threshold_breach` | `merchant_id`, `as_of` | projected crossing date, lead days, threshold, exclusively-exempt flag | Evidence | P0 |
| 9 | `isolate_disputed_credit` | `merchant_id`, `utr?`, `amount?`, `date?` | matched credit, other candidates, sale record | Evidence | P0 |
| 10 | `build_evidence_pack` | `merchant_id`, `kind` (`tax`\|`freeze`), `ref` | structured pack, every line traceable to txn_ids | Evidence | P0 |
| 11 | `map_hsn_exemption` | `items[]` | per item exempt/taxable + basis | Evidence | P1 |
| 12 | `detect_return_mismatch` | `merchant_id` | declared vs computed per quarter | Evidence | P1 |
| 13 | `draft_ncrp_grievance` | `merchant_id`, `txn_id`, `case_ref` | grievance draft text | Evidence | P1 |

Arithmetic lives in the tools, not in the model. The service returns rows and compact rollups; tools do the maths so the workings appear in the Phinite trace.

## Permission boundaries (PLAN §5 → tool policies)

| Agent node | Policy |
|---|---|
| Provenance | Allow 1–4. **Deny `commit_attestation`.** |
| Merchant | Allow `commit_attestation`, 1, 6. |
| Evidence | Allow 7–13 (all read-only). Deny 4 and 5. |
| Escalation | **Human approval** on `build_evidence_pack` delivery → Dashboard approvals queue. |

Attach each with "Apply to: One agent", not the whole flow. The deny-by-default on unlisted actions does the rest.

## Data service

FastAPI on Render, seeded by running the generator at build time, so no data is committed and the demo IDs always match DATA.md.

| Endpoint | Purpose |
|---|---|
| `GET /health` | liveness |
| `GET /merchants`, `GET /merchants/{mid}` | profile, linked own accounts |
| `GET /credits` | visible ledger, filterable by merchant/date, paginated |
| `GET /credits/{txn_id}`, `GET /credits/by_utr/{utr}` | one credit + POS bill |
| `GET /payer_history` | payer aggregates for one counterparty |
| `GET /events` | tax notice, freeze, declared returns |
| `GET /ledger`, `GET /ledger/rollup` | tags; rollup by label/day for turnover maths |
| `POST /ledger/propose` | Provenance writes a proposed tag |
| `POST /ledger/attest` | Merchant commits an attested tag (separate key) |
| `GET /attestation_queue` | ≤3 ambiguous credits for a day |

`hidden/` is never served. The service reads `visible/` only; ground truth stays out of the runtime path.

## Demo checklist (rehearse in this order)

1. **Ordinary Tuesday** — 10 Mar 2026, three credits, one tap each, ledger updates.
2. **The warning** — replay as of 31 Jan 2026, projection lands near 14 Mar 2026, tells her to register, routes to a CA.
3. **The notice** — ₹60.98L claimed, pack shows ₹42.9L aggregate turnover, every line clickable to a txn_id in the trace.
4. **The emergency** — freeze at 09:30 on 24 Mar, isolate ₹4,200 (UTR `608019013171`) out of 339 that week, reject the decoy, draft the grievance, Escalation holds delivery for human approval.

Expected values are in `data/demo/hidden/demo_scenario.json`. Every beat needs a static fallback.

## Track A setup checklist

1. Workspace + roles (PROD promotion may need Admin/SuperAdmin).
2. Create `hisaab-merchant` (Conversational) and `hisaab-watch` (Autonomous).
3. Dev Studio: publish `get_credit` first; test it with a real `txn_id` from the demo split.
4. Env variables per environment: `HISAAB_API`, `HISAAB_KEY`, `HISAAB_ATTEST_KEY`.
5. Integrations → Channels → Web Chat; deploy DEV build; check the widget answers.
6. Tool policies per the table above; verify a denied call actually fails in the trace.
7. Cron trigger on `hisaab-watch` for the nightly pass.
8. Agent Registry: expose Evidence as an Agent Card with skills and tags.
