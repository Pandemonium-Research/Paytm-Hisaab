# BUILD_PLAN.md — hackathon day

Companion to [PLAN.md](PLAN.md) (what we're building and why) and [DATA.md](DATA.md) (the data).
This file is the running order, who does what, and the contract between the two tracks.

## Decisions (locked)

| Decision | Choice | Why |
|---|---|---|
| Channel | **Web Chat** | No Meta/BSP credentials or webhook verification. Revisit WhatsApp only if credentials are in hand by midday. |
| Data service host | **Render** | Public HTTPS that survives a laptop sleeping. ngrok tunnel is the backup. |
| Demo data | **Synthetic** (`data/demo`) | Calibrated to the four beats. Show a Paytm sandbox read separately, as proof it connects. |

## Status

**Track B — done and verified locally**

- **Data service.** One implementation, built from both: the teammate's store and `get_credit`
  kept, with three additions ported in — the `ask` flag (materiality), `/merchant_mix` (exempt
  share, for apportioning unbilled QR sales) and gross totals in the rollup — plus `/untagged`
  for the nightly pass. Fixed `/hsn`, which returned a list under a `dict` annotation and 500'd.
- **Tools 1–10** written, adapted to the live service, exercised end to end (`tools/run_local.py`).
- **`simulate_year`**: a year of nightly passes plus a stand-in merchant answering the queue —
  **189 questions across the year, median 1.3/day, none over the ≤3/day budget**, 0 credits left
  untagged, merchant corrected 52.
- **`check_beats`**: all four beats pass.
  - beat 1 — the queue asked on 10 Mar surfaces exactly the three seeded credits and nothing else
  - beat 2 — projection from 31 Jan lands within a day of 14 Mar, ~6 weeks of warning
  - beat 3 — aggregate turnover within **1.6%** of truth against the ₹60.98L claim, and the
    taxable share within **1%** (unbilled QR sales are apportioned by value from the billed
    ratio; labelling each one by its majority side understated taxable turnover threefold,
    which is the one direction PLAN §7 says we must never drift)
  - beat 4 — ₹4,200 isolated by UTR *and* by amount+date, decoy listed but not chosen

**Track B — next**

1. ~~Deploy the service to Render~~ — **done**, `https://hisaab-data-service.onrender.com`,
   `auth: keyed`, 13,267 ledger rows, reachable from inside Phinite's sandbox.
   Step by step, with the verification curls and the free-plan traps: [DEPLOY.md](DEPLOY.md).
2. P1 tools: `map_hsn_exemption` and `draft_ncrp_grievance`. **`detect_return_mismatch` is
   cut** — see below.
3. Provenance agent prompt: when to take the rule label, when to ask, how to word the reason.
4. Phinite Evaluations dataset from the eval split.

### Why `detect_return_mismatch` is cut

It has nothing to fire on in the demo. `declared_returns()` in the generator only runs for
`gst == "composition"`, and only the `composition_kirana` archetype carries that. Sahana
inherits `unregistered` from `_BASE`, so `data/demo` holds exactly two events:
`account_frozen` and `tax_notice`. That is correct by design — an unregistered trader files
no returns — but it means the tool can never run in any of the four beats. It costs build
time and buys no stage moment.

**The gap this leaves, and the answer to have ready.** That tool is PLAN Module A's second
half: "tracks the gap between Paytm-collected receipts and what the merchant has declared,
which is exactly the reconciliation authorities now perform" ([PLAN.md](PLAN.md) §3). Cutting
it means the demo shows the threshold projection but not the mismatch detection. If a judge
asks:

> The mismatch check runs against a registered composition dealer, because that is who files
> a CMP-08 to disagree with. Our demo merchant is unregistered, so she has no returns to
> reconcile — that is the whole reason she gets a notice. The `composition_kirana` merchant in
> our dev and eval splits has four quarters of under-declared CMP-08 returns seeded, and the
> same ledger answers it.

Better to say that than to discover the gap on stage.

**Track A — with the teammate**: Phinite workspace, graphs, publishing tools, policies, Web Chat,
builds, registry, observability, rehearsal.

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
- **Track B — Python (us).** Data service, tool handlers, classifier rules and prompts, evaluation numbers.

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
# ENV_VARS: ["HISAAB_API", "HISAAB_KEY"]

def main(inputs, env_variables):
    return {"output": {...}, "capture_variables": {...}, "captured_variables": {...}}
```

Track B writes each handler in `tools/<tool_name>.py` with exactly that signature, tested locally. Track A pastes it into Dev Studio, sets the parameter schema, tests, publishes.

Three things about the contract, measured in the sandbox rather than assumed (`tools/_sandbox_check.py`,
published and tested in Dev Studio):

- **Egress works.** A tool reached `https://api.github.com` and got a 200, so the whole
  data-service architecture stands. This was the one unknown that could have killed it.
- **The `# ENV_VARS: [...]` header is a declaration, not an allowlist.** A tool can read every
  variable set on its environment, including ones it never named: `_sandbox_check` declares
  `HISAAB_API` and `HISAAB_KEY` and sees `HISAAB_ATTEST_KEY` too. An earlier run of the same
  tool showed only its two declared variables, but that was because only those two were set at
  the time — not because the header filtered anything.

  **This makes scoping `HISAAB_ATTEST_KEY` to `hisaab-merchant` load-bearing, not
  belt-and-braces.** Any tool on a graph where the commit key is set can read it out of
  `env_variables` and attest directly, whatever its own header says. The boundary rests on the
  Phinite tool policy denying Provenance `commit_attestation`, plus not putting the key within
  its reach in the first place. The service's 403 only catches a tool that uses the read key.
- **Both capture keys are returned.** Phinite reads one of `capture_variables` /
  `captured_variables` and ignores the other; Aura generates the first, our plan assumed the
  second, and the Dev Studio tool test echoes the return verbatim so it cannot settle which.
  Every handler emits both. Costs nothing, and avoids variables silently failing to pass
  between nodes.

Sandbox: Python 3.12.14, with `requests`, `httpx` and `sqlite3` available. Handlers still use
only the standard library, so nothing depends on that staying true.

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
| 6 | `get_attestation_queue` | `merchant_id`, `date`, `lookback_days`, `max_items=3` | ≤3 ambiguous credits with proposal and reason | Merchant | P0 |
| 7 | `compute_aggregate_turnover` | `merchant_id`, `fy`, `as_of?` | taxable + exempt total, excluded buckets, workings | Evidence | P0 |
| 8 | `project_threshold_breach` | `merchant_id`, `as_of` | projected crossing date, lead days, threshold, exclusively-exempt flag | Evidence | P0 |
| 9 | `isolate_disputed_credit` | `merchant_id`, `utr?`, `amount?`, `date?` | matched credit, other candidates, sale record | Evidence | P0 |
| 10 | `build_evidence_pack` | `merchant_id`, `kind` (`tax`\|`freeze`), `ref` | structured pack, every line traceable to txn_ids | Evidence | P0 |
| 11 | `map_hsn_exemption` | `items[]` | per item exempt/taxable + basis | Evidence | P1 |
| 12 | `detect_return_mismatch` | `merchant_id` | declared vs computed per quarter | Evidence | P1 |
| 13 | `draft_ncrp_grievance` | `merchant_id`, `txn_id`, `case_ref` | grievance draft text | Evidence | P1 |

Arithmetic lives in the tools, not in the model. The service returns rows and compact rollups; tools do the maths so the workings appear in the Phinite trace.

**Built:** 1–10, all verified against the live service. **Outstanding:** 11–13 (P1).
Per-tool parameters, descriptions and Dev Studio test values: [phinite/TOOL_SCHEMAS.md](phinite/TOOL_SCHEMAS.md).
Why the classifier asks what it asks: [tools/README.md](tools/README.md).

## Permission boundaries (PLAN §5 → tool policies)

| Agent node | Policy |
|---|---|
| Provenance | Allow 1–4. **Deny `commit_attestation`.** |
| Merchant | Allow `commit_attestation`, 1, 6. |
| Evidence | Allow 7–13 (all read-only). Deny 4 and 5. |
| Escalation | **Human approval** on `build_evidence_pack` delivery → Dashboard approvals queue. |

Attach each with "Apply to: One agent", not the whole flow. The deny-by-default on unlisted actions does the rest.

## Data service

FastAPI on Render, seeded by running the generator *and* `simulate_year` at build time, so no
data is committed, the demo IDs always match DATA.md, and a free-plan restart restores the year
of proposals rather than emptying it. Deployment steps: [DEPLOY.md](DEPLOY.md).

| Endpoint | Purpose |
|---|---|
| `GET /health` | liveness |
| `GET /merchants`, `GET /merchants/{mid}` | profile, linked own accounts |
| `GET /credits` | visible ledger, filterable by merchant/date, paginated |
| `GET /credits/{txn_id}`, `GET /credits/by_utr/{utr}` | one credit + POS bill + its ledger tag |
| `GET /credits/{txn_id}/twins` | identical payments nearby, and any refund pointing at it |
| `GET /payer_history` | payer aggregates for one counterparty |
| `GET /merchant_mix` | exempt share of POS-billed value, for apportioning unbilled QR sales |
| `GET /hsn` | the public HSN catalogue |
| `GET /events` | tax notice, freeze, declared returns |
| `GET /untagged` | credits with no tag yet — the nightly pass's work queue |
| `GET /ledger`, `GET /ledger/rollup` | tags; rollup by label and day, plus gross and untagged totals |
| `POST /ledger/propose` | Provenance writes a proposed tag (`ask` puts it in the queue) |
| `POST /ledger/attest` | Merchant commits an attested tag (separate key) |
| `GET /attestation_queue` | ≤3 flagged credits from the days before `date` |

Auth is the `X-Hisaab-Key` header. `hidden/` is never served: `store._visible()` refuses any path
containing it, so ground truth stays out of the runtime path.

## Demo checklist (rehearse in this order)

1. **Ordinary Tuesday** — 10 Mar 2026, three credits, one tap each, ledger updates.
2. **The warning** — replay as of 31 Jan 2026, projection lands near 14 Mar 2026, tells her to register, routes to a CA.
3. **The notice** — ₹60.98L claimed, pack shows ₹42.9L aggregate turnover, every line clickable to a txn_id in the trace.
4. **The emergency** — freeze at 09:30 on 24 Mar, isolate ₹4,200 (UTR `608019013171`), reject the
   decoy `DM0012998`, draft the grievance, Escalation holds delivery for human approval. Say "339
   payments in the week before the freeze" (the scenario's own figure); the tool reports 409 for
   the seven days ending on the disputed payment itself, which is a different window.

Expected values are in `data/demo/hidden/demo_scenario.json`. Every beat needs a static fallback.

### Before the demo, not before that

Two things deliberately left for later. Both are easy to forget and both break beat 1.

1. **Scope `HISAAB_ATTEST_KEY` to `hisaab-merchant`.** It is currently set workspace-wide,
   because until the merchant graph exists there is nowhere else to put it. While it stays
   that way `hisaab-watch` can commit attestations: a Provenance test run that calls
   `commit_attestation` will succeed and silently spend credits out of the beat-1 queue. If
   beat 1 starts surfacing two credits instead of three, this is why.
2. **Restore the queue.** Render → Manual Deploy → **Clear build cache & deploy** (3–5 min)
   re-runs the seed and puts all three 8–9 Mar credits back as `proposed`. Needed after any
   rehearsal that taps through beat 1, and needed now: a connectivity probe attested
   `DM0012559` on 12 Sep.

Check the queue is whole before going on stage:

```bash
curl -s -H "X-Hisaab-Key: $HISAAB_KEY" \
  "$HISAAB_API/attestation_queue?merchant_id=MID_DEMO_SAHANA&date=2026-03-10&lookback_days=2&max_items=3"
```

`pending_total` must be 3.

## Track A setup checklist

1. Workspace + roles (PROD promotion may need Admin/SuperAdmin).
2. Create `hisaab-merchant` (Conversational) and `hisaab-watch` (Autonomous).
3. Dev Studio: publish `get_credit` first; test it with a real `txn_id` from the demo split.
4. Env variables per environment: `HISAAB_API`, `HISAAB_KEY`, `HISAAB_ATTEST_KEY`.
5. Integrations → Channels → Web Chat; deploy DEV build; check the widget answers.
6. Tool policies per the table above; verify a denied call actually fails in the trace.
7. Cron trigger on `hisaab-watch` for the nightly pass.
8. Agent Registry: expose Evidence as an Agent Card with skills and tags.
