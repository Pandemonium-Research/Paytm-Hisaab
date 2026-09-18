# n8n

Workflow JSON lives in `workflows/`, one file per workflow, exported with
`python tasks.py export-n8n --target cloud|local`. The design is in
[IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md) §10.

## Instance (task 0.1, checked 18 Sep 2026)

| Item | Value | Source |
|---|---|---|
| Plan | n8n Cloud **Pro**, from the hackathon voucher, for one month | voucher |
| Executions | **10,000 a month.** An execution is one run of a whole workflow, however many steps. Over the quota, workflows keep running but "overage charges may apply". | [pricing](https://n8n.io/pricing/) |
| Concurrency | **20 production executions** (started by a webhook or trigger). Extra ones queue and run first in, first out. Manual, sub-workflow and error executions don't count. | [Understand concurrency](https://docs.n8n.io/deploy/use-n8n-cloud/understand-concurrency.md) |
| Execution log retention | 7 days | pricing |
| Test evaluations | One test case at a time on Pro | Understand concurrency |
| Public API | Included on Pro (not on the trial). Header `X-N8N-API-KEY`, base `https://<name>.app.n8n.cloud/api/v1`. Below Enterprise there are no scopes, so the key has full access to the instance. **Checked:** `GET /api/v1/workflows` returned 200 on 18 Sep. | [Authentication](https://docs.n8n.io/connect/n8n-api/authentication.md) |
| API key | Created 18 Sep 2026, **expires 16 Dec 2026**; stored in `.env.live` only | read from the key |
| Instance URL | `https://pandemonium-research.app.n8n.cloud` (`N8N_BASE_URL`) | |
| Instance version | **n8n@2.39.7**, which meets the 2.6 minimum for human review of AI tool calls (§10). The compose `local-n8n` profile pins the same image (`n8nio/n8n:2.39.7`) so workflow JSON round-trips cleanly. | admin dashboard |
| Usage | 0 / 10,000 executions in September (18 Sep) | admin dashboard |
| Gateway credits | $2.00. **Don't use them:** AI nodes use our own Sarvam credential, never n8n's built-in model gateway. | admin dashboard |

## What this means for the build

- **Executions aren't the constraint.** The live-window budget in §16a is 135 executions in
  total, about 1.4% of the month. Keep to it anyway, so the voucher never runs into overage.
- **Twilio must call the production URL** (`/webhook/...`), which exists only while the
  workflow is published. The test URL (`/webhook-test/...`) listens only while the editor is
  waiting for a test event.
- **Twilio can't send custom headers.** WF31's webhook therefore uses no n8n auth and checks
  `X-Twilio-Signature` in its first Code node. Webhooks that core calls use Header Auth with
  `N8N_WEBHOOK_SECRET`.
- **Answer Twilio at once** (response mode "Immediately") and send the reply through the
  Messages API from WF30. Twilio gives up on a webhook after 15 s, and a Sarvam call plus the
  guards can take longer.
- **The webhook payload limit is 16 MB.** Twilio sends media as URLs, so this only matters for
  uploads from the app, which go to core, not to n8n.
- **WF10-eval (9.9) runs its ~50 cases one after another**, because Pro evaluates one test case
  at a time.
- **Execution logs last 7 days.** Screenshots and exports for the n8n prize (12.8) come from the
  L2, L4 and L5 runs, all inside that window.

## Credentials to create

Local n8n (development, task 5.2): one HTTP Header Auth per role key, plus Sarvam and Twilio
pointed at `FAKES_URL`. n8n Cloud (live, task 10.1b): the same set with the real keys from
`.env.live`.

## Workflows (task 1.5)

Draft by B, 18 Sep. Frozen at Phase 1 sign-off; after that, changes need A's OK in chat
(LANES.md §2).

Role keys are `X-Hisaab-Key` header values (plan §7). Each is a separate n8n HTTP Header Auth
credential. **A workflow may hold more than one** — nodes carry the credential for the role that
node's endpoint needs, so no workflow ever gets a wider key than its narrowest step allows.

| ID | Trigger | Inputs | Outputs | Role key(s) |
|---|---|---|---|---|
| **WF10** nightly-provenance | Schedule 02:00 IST · webhook from core | `{merchant?, as_of, mode, from?, to?}` | `label.proposed` (batch), `question.asked` via WF30, threshold warning | `provenance` (classify-rules, proposals, select-questions) · `evidence` (threshold) |
| **WF30** merchant-outbound (sub) | Execute Workflow | `{merchant_id, template, lang, slots{}, channel, txn_id?}` | Twilio message or `/assistant/outbound`; `question.asked` | `conversation` |
| **WF31** merchant-inbound | Twilio webhook · `/assistant/inbound` webhook | Twilio form-encoded body, or assistant JSON | `claim.answered` / `claim.annotated` / `label.disputed`; reply via WF30 | `conversation` |
| **WF20** freeze-response | Core webhook `case.opened` (freeze) | `{case_id, merchant_id, opened_at, trigger}` | `pack.built`, then `pack.sent` after approval | `evidence` (isolate, tiers, escalation, packs) · `officer` (outbox send after the Wait) |
| **WF21** lea-inquiry (P1) | Core webhook `lea_inquiry` | `{case_id, merchant_id, inquiry_ref, as_of}` | Officer approval → outbox reply. **No WF30 node exists here** — asserted by beat B6 | `evidence` · `officer` |
| **WF40** notice-response | WF31, or core webhook `notice_served` | `{merchant_id, media_url \| media_sha256, source}` | `NoticeExtraction`, tax pack, explainers | `evidence` |
| **WF50** escalation-handoff (sub) | Execute Workflow | `{case_id, reasons[], merchant_id}` | `HandoffSummary` → officer queue; WF30 notice to merchant | `evidence` |
| **WF60** daily-anchor | Schedule 23:55 IST · called by WF10 in seed mode | `{as_of}` | `anchor.created` | `admin` |
| **WF90** error-handler | n8n error workflow (set on every workflow) | n8n error payload | `ops` log row, officer alert card | `admin` |
| **WF99** refusal-probe | Manual (demo) | none | The 403 body, shown on stage | `evidence` (deliberately the wrong key) |

### Webhook payloads core sends to n8n

Every core → n8n call is fire-and-forget, carries `X-N8N-Webhook-Secret: $N8N_WEBHOOK_SECRET`,
and the workflow answers immediately with **Respond to Webhook** before doing any work (§10.2:
core must not wait on n8n).

```jsonc
// POST {N8N_BASE_URL}/webhook/hisaab/wf10-nightly
{ "merchant_id": "MID_DEMO_BLR" | null,   // null = every merchant
  "as_of": "2026-03-10T02:00:00+05:30",
  "mode": "live" | "seed",
  "from": "2026-03-09", "to": "2026-03-10" }   // seed mode only

// POST {N8N_BASE_URL}/webhook/hisaab/wf20-freeze
{ "case_id": "CASE_0007", "merchant_id": "MID_DEMO_BLR",
  "opened_at": "2026-03-24T09:30:00+05:30",
  "trigger": "lien_marked" | "declines_then_lien" }

// POST {N8N_BASE_URL}/webhook/hisaab/wf21-lea
{ "case_id": "CASE_0009", "merchant_id": "MID_DEMO_BLR",
  "inquiry_ref": "LEA/2026/0211", "as_of": "2026-02-11T11:00:00+05:30" }

// POST {N8N_BASE_URL}/webhook/hisaab/wf40-notice
{ "merchant_id": "MID_DEMO_BLR", "media_sha256": "…", "media_url": "…",
  "source": "rails_event" | "wf31_upload" }
```

**WF31 is the exception:** Twilio cannot send custom headers, so its webhook has no n8n auth and
validates `X-Twilio-Signature` in a Code node instead (see "What this means for the build").

### Decisions (18 Sep)

**Answer choices: the plan as written, per channel.** All 7 values of
`sim.catalog.ANSWER_CHOICES` stay in the enum; each channel shows a subset:

| Channel | Shown | Source |
|---|---|---|
| WhatsApp numbered reply | `1 sale · 2 family · 3 my own money · 4 not sure` | plan §11, PHASES 2C.4 |
| App chips (M2) | the 4 above + `loan / other` | plan §12.2 |
| Voice note or free text, either channel | any of the 7 | plan §11: the parser accepts a digit, a word or a voice note |

Measured on the rules baseline with the §7 question-budget rules (eval and dev splits, about 670
question candidates each): the 4 numbered options cover **90.5%** of truthful answers, and the
app's 5 cover **94%**. `not_sure` is safe by design, since the credit stays machine-labelled and is
never guessed (§7). The rules settle refunds on their own (100%, 42/42) but only **43–51%** of
duplicates, even with the §21 fix. That's why `double_payment` stays reachable by voice and text
rather than being dropped.

**Role keys per node, not per workflow.** WF10 carries `provenance` for labelling and `evidence`
for the threshold check, as in the table above. This is n8n wiring only; the plan's role matrix
(§14) is unchanged.

## Spike results (2B, window L1)

*One line per check S1–S8: go or no-go, and the fallback chosen if it failed.*
