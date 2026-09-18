# Core contracts

This is the Phase 1 hand-off for Lane B. Python names are exported from
`app.schemas` and `app.schemas.api`. Money fields are integer rupees. All datetimes are aware
ISO-8601 values. Request objects never contain `recorded_at`.

## Ledger entry kinds

| Kind | Payload |
|---|---|
| `credit.observed` | `amount`, `channel`, `counterparty_id` |
| `bill.linked` | `bill_id`, `line_count`, `total` |
| `label.proposed` | `label`, `source`, rule or model metadata, `confidence`, `reason`, evidence and memory refs |
| `question.asked` | `question_id`, `text`, `language`, `expires_at` |
| `claim.answered` | `question_id`, `answer` (what they tapped), one of `raw_text` or `media_sha256`, `language` |
| `claim.annotated` | `label`, `raw_text`, `language` |
| `label.disputed` | `disputed_label`, `reason` |
| `case.opened` | `case_id`, `case_type`, `trigger_ref` |
| `pack.built` | `pack_id`, `pdf_sha256`, tier amount/count totals |
| `pack.approved` | `pack_id`, optional note |
| `pack.rejected` | `pack_id`, reason |
| `pack.sent` | `pack_id`, destination, delivery ref |
| `anchor.created` | `anchor_id`, digest, simulated flag, optional OTS and git refs |

Every entry also has `seq`, `merchant_id`, `chain_index`, nullable `txn_id`, `actor_role`,
`actor_ref`, `sim_at`, `recorded_at`, `prev_hash` and `hash`. `kind` discriminates the payload.
The database supplies `recorded_at`. Hashing is specified in `schemas/ledger.py` and is implemented
in task 2A.5.

Evidence tiers are: 1 bill-backed, 2 rule-derived, 3 the merchant's pre-case answer, and 4 an
annotation or evidence recorded after the case opened.

`claim.answered` records only the merchant's `AnswerChoice`, never a label inferred by the
system. `current_view` resolves that answer through `ANSWER_TO_LABELS`: `sale` retains the
machine's taxable or exempt supply label, as decided by the bill or the shop's billed exempt
share; each other definite answer resolves to its single label; `not_sure` resolves to nothing
and leaves the machine label in force. `claim.annotated` still records the label named by the
merchant in an explicit correction.

## Roles

| Role | May append | Main calls | Cannot |
|---|---|---|---|
| rails | `credit.observed`, `bill.linked`, `case.opened` | rails ingest | label, claim, approve |
| provenance | `label.proposed` | reads, classify, proposals, question selection | claim, build or approve packs |
| conversation | `question.asked`, `claim.answered`, `claim.annotated`, `label.disputed` | reads, questions, claims, merchant assistant | propose labels, build or approve packs |
| evidence | `case.opened`, `pack.built` | reads, evidence skills, cases, packs | change labels or claims, approve, send |
| officer | `pack.approved`, `pack.rejected`, `pack.sent` | approve, reject, send, trust views | label or claim |
| admin | `anchor.created` | simulator and anchor controls | label, claim, build or approve packs |
| app | nothing | merchant PWA reads, profile, assistant inbound and stream | append any ledger entry |

`ROLE_ENTRY_KINDS` and `ENDPOINT_PERMISSIONS` are executable data in `schemas/roles.py`.

## Endpoints

| Endpoint | Body model | Response model | Roles |
|---|---|---|---|
| `POST /rails/credits` | `RailsCreditsRequest` | `RailsCreditsResponse` | rails |
| `POST /rails/debits` | `RailsDebitsRequest` | `RailsDebitsResponse` | rails |
| `POST /rails/bills` | `RailsBillsRequest` | `RailsBillsResponse` | rails |
| `POST /rails/events` | `RailsEventsRequest` | `RailsEventsResponse` | rails |
| `GET /merchants/{id}` | — | `MerchantResponse` | provenance, conversation, evidence |
| `GET /credits` | — | `CreditsResponse` | provenance, conversation, evidence |
| `GET /credits/{txn}` | — | `CreditResponse` | provenance, conversation, evidence |
| `GET /credits/by-utr/{utr}` | — | `CreditByUtrResponse` | provenance, conversation, evidence |
| `GET /payers/{cp}/history` | — | `PayerHistoryResponse` | provenance, conversation, evidence |
| `POST /skills/classify-rules` | `ClassifyRulesRequest` | `ClassifyRulesResponse` | provenance |
| `POST /ledger/proposals` | `LedgerProposalRequest` | `LedgerProposalResponse` | provenance |
| `POST /skills/select-questions` | `SelectQuestionsRequest` | `SelectQuestionsResponse` | provenance |
| `POST /ledger/questions` | `LedgerQuestionRequest` | `LedgerQuestionResponse` | conversation |
| `POST /ledger/claims` | `LedgerClaimRequest` | `LedgerClaimResponse` | conversation |
| `POST /skills/turnover` | `TurnoverRequest` | `TurnoverResponse` | evidence |
| `POST /skills/threshold` | `ThresholdRequest` | `ThresholdResponse` | evidence |
| `POST /skills/isolate` | `IsolateRequest` | `IsolateResponse` | evidence |
| `POST /skills/tiers` | `TiersRequest` | `TiersResponse` | evidence |
| `POST /skills/escalation-check` | `EscalationCheckRequest` | `EscalationCheckResponse` | evidence |
| `POST /cases` | `CreateCaseRequest` | `CreateCaseResponse` | evidence |
| `POST /packs` | `BuildPackRequest` | `BuildPackResponse` | evidence |
| `POST /guards/numbers` | `GuardRequest` | `GuardResponse` | all roles |
| `POST /guards/citations` | `GuardRequest` | `GuardResponse` | all roles |
| `POST /guards/no-innocence` | `GuardRequest` | `GuardResponse` | all roles |
| `POST /guards/extraction` | `GuardRequest` | `GuardResponse` | all roles |
| `POST /guards/language` | `GuardRequest` | `GuardResponse` | all roles |
| `POST /packs/{id}/approve` | `ApprovePackRequest` | `ApprovePackResponse` | officer |
| `POST /packs/{id}/reject` | `RejectPackRequest` | `RejectPackResponse` | officer |
| `POST /outbox/{pack}/send` | `SendPackRequest` | `SendPackResponse` | officer |
| `GET /ledger/verify` | — | `LedgerVerifyResponse` | officer, admin |
| `GET /ledger/{m}/entries` | — | `LedgerEntriesResponse` | officer, admin |
| `GET /anchors` | — | `AnchorsResponse` | officer, admin |
| `POST /sim/clock` | `SimClockRequest` | `SimClockResponse` | admin |
| `POST /sim/replay` | `SimReplayRequest` | `SimReplayResponse` | admin |
| `POST /sim/reset` | `SimResetRequest` | `SimResetResponse` | admin |
| `POST /sim/tamper` | `SimTamperRequest` | `SimTamperResponse` | admin |
| `POST /anchors/run` | `RunAnchorRequest` | `RunAnchorResponse` | admin |
| `POST /assistant/inbound` | `AssistantInboundRequest` | `AssistantInboundResponse` | app |
| `GET /assistant/stream` | — | `AssistantStreamResponse` | app |
| `POST /assistant/outbound` | `AssistantOutboundRequest` | `AssistantOutboundResponse` | conversation |
| `GET /app/home` | — | `AppHomeResponse` | app |
| `GET /app/questions` | — | `AppQuestionsResponse` | app |
| `GET /app/payments` | — | `AppPaymentsResponse` | app |
| `GET /app/payments/{txn}` | — | `AppPaymentDetailResponse` | app |
| `GET /app/cases` | — | `AppCasesResponse` | app |
| `GET /app/turnover` | — | `AppTurnoverResponse` | app |
| `PUT /app/profile` | `AppProfileRequest` | `AppProfileResponse` | app |
| `GET /app/officer/queue` | — | `OfficerQueueResponse` | officer |
| `GET /app/officer/cases/{id}` | — | `OfficerCaseResponse` | officer |
| `GET /app/officer/outbox` | — | `OfficerOutboxResponse` | officer |
| `POST /app/push/subscribe` | `PushSubscribeRequest` | `PushSubscribeResponse` | app, officer |
| `GET /prompts/{name}` | — | `PromptResponse` | all roles |
| `GET /config` | — | `ConfigResponse` | all roles |

The same mapping is available as `ENDPOINT_MODELS`. Path and query values are handled by the
route. A dash therefore means there is no JSON body, not that the route has no inputs.

`POST /rails/credits` accepts only `CR` transactions on the simulator's credit channels.
`POST /rails/debits` accepts only `DR` transactions on `UPI_OUT` or `REFUND`; debits have no
bill link, bill lines or label. Debit ingestion adds no ledger kind: the thirteen evidence kinds
remain frozen.

`AnswerChoice` is the only answer enum. WhatsApp numbered replies show `sale`, `family`,
`own_money` and `not_sure`; M2 shows those four plus `loan_or_gift`; voice and free text can
resolve to all seven values. `GET /app/questions` returns exactly five distinct localized chips
per card, plus amount and `amount_text`, time, payer, channel, localized question, position and
total, and the automatically-settled count and closing line.

`PUT /app/profile` saves `language`, `consent_at` and `consent_text_version` as ops working
state and echoes that state with `saved` in `AppProfileResponse`. Consent creates no ledger entry.
`GET /app/officer/outbox` returns the simulated delivery stamp, outcome and usable balance, plus
explicit `freeze_to_pack_seconds` and `pack_to_approval_seconds` durations alongside its
timestamps.

## Short examples

Rails ingest:

```json
{"transactions":[{"txn_id":"DM0000001","merchant_id":"MID_DEMO_SAHANA","ts":"2026-03-21T19:47:00+05:30","direction":"CR","amount":4200,"channel":"UPI_POS","counterparty_id":"P123","counterparty_handle":"payer@upi","counterparty_name":"PAYER","terminal_id":"POS01","pos_bill_id":"BDM0000001","utr":"608119000001","note":""}]}
```

```json
{"accepted":1,"duplicate_txn_ids":[]}
```

Read:

```json
{"transaction":{"txn_id":"DM0000001","merchant_id":"MID_DEMO_SAHANA","ts":"2026-03-21T19:47:00+05:30","direction":"CR","amount":4200,"channel":"UPI_POS","counterparty_id":"P123","counterparty_handle":"payer@upi","counterparty_name":"PAYER","terminal_id":"POS01","pos_bill_id":"BDM0000001","utr":"608119000001","note":""},"machine_label":"taxable_supply","claim_label":null,"effective_label":"taxable_supply","tier":1,"conflict":false,"entry_refs":[7]}
```

Provenance and question selection:

```json
{"merchant_id":"MID_DEMO_SAHANA","txn_id":"DM0000001","proposal":{"label":"taxable_supply","source":"agent","model":"sarvam","prompt_version":"v1","confidence":0.85,"reason":"Payment evidence indicates a sale.","evidence_refs":[],"memory_refs":[]},"sim_at":"2026-03-21T20:00:00+05:30"}
```

```json
{"selected":[{"txn_id":"DM0000001","payer_id":"P123","priority":630.0,"expires_at":"2026-03-28T20:00:00+05:30"}],"expired_txn_ids":[],"remaining_daily_budget":2}
```

Conversation:

```json
{"merchant_id":"MID_DEMO_SAHANA","txn_id":"DM0000001","action":"answered","claim":{"question_id":"Q1","answer":"sale","raw_text":"It was a sale.","language":"en"},"sim_at":"2026-03-22T09:00:00+05:30"}
```

Evidence skill:

```json
{"merchant_id":"MID_DEMO_SAHANA","case_id":"C1","disputed_utr":"608119000001","disputed_amount":4200,"disputed_date":"2026-03-21","date_window_days":1,"as_of":"2026-03-24T09:30:00+05:30"}
```

```json
{"matched":null,"found_by":[],"same_amount_candidates":[],"bill":null,"device":null,"seven_day_credit_count":339}
```

Case and officer action:

```json
{"officer_ref":"OFFICER01","note":"Evidence checked.","sim_at":"2026-03-24T10:00:00+05:30"}
```

```json
{"pack_id":"PK1","status":"approved","workflow_resumed":true,"ledger_entry":{"seq":12,"merchant_id":"MID_DEMO_SAHANA","chain_index":11,"kind":"pack.approved","txn_id":null,"payload":{"pack_id":"PK1","note":"Evidence checked."},"actor_role":"officer","actor_ref":"OFFICER01","sim_at":"2026-03-24T10:00:00+05:30","recorded_at":"2026-09-18T13:00:00+05:30","prev_hash":"...","hash":"..."}}
```

Guard:

```json
{"text":"The disputed amount is Rs 4,200.","context":{"disputed_amount":4200}}
```

```json
{"guard":"numbers","passed":true,"offending_spans":[]}
```

Simulator:

```json
{"sim_at":"2026-03-24T09:30:00+05:30"}
```

```json
{"sim_at":"2026-03-24T09:30:00+05:30"}
```

Assistant:

```json
{"merchant_id":"MID_DEMO_SAHANA","message_id":"M1","content_type":"text","text":"Show my case","sim_at":"2026-03-24T09:35:00+05:30"}
```

```json
{"accepted":true,"conversation_id":"CONV1","forwarded_to_workflow":true}
```

App read model:

```json
{"merchant_id":"MID_DEMO_SAHANA","business_name":"Sahana Stores","as_of":"2026-03-24T09:35:00+05:30","balance":{"amount":12500,"amount_text":"Rs 12,500"},"today_received":{"amount":4200,"amount_text":"Rs 4,200"},"questions_due":1,"open_cases":1,"alerts":[]}
```

Prompt and config reads:

```json
{"name":"hard-case-label","version":"v1","text":"…","sha256":"…"}
```

```json
{"environment":"local","live":false,"default_locale":"en-IN","supported_locales":["en-IN","kn-IN"],"vapid_public_key":null}
```

## Question and escalation constants

Question candidates and sorting use the named constants in `schemas/api/skills.py`: confidence
below 0.75; non-sale credits from Rs 10,000; new-payer sales from Rs 3,000 with at most three
strictly prior credits and no bill; never below Rs 500; 1.5 proximity multiplier within 15%;
three questions a day; seven-day expiry.

Escalation uses the provisional Rs 50,000 small-sum limit, tiers 3–4 as weak evidence, a 40%
weak-evidence share, and a 90-day repeat-freeze window. The constants remain marked for section
22 verification.

## Cassette format

`ProviderCassette` records `provider`, `endpoint`, a SHA-256 `request_key`, the full normalised
request, response status/headers/body, `live_window` (`L1`–`L5`) and `recorded_at`.

```json
{
  "schema_version": 1,
  "provider": "sarvam",
  "endpoint": "/v1/chat/completions",
  "request_key": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "normalised_request": {
    "method": "POST",
    "path": "/v1/chat/completions",
    "query": {},
    "headers": {"content-type": "application/json"},
    "body": {"model": "sarvam-m", "messages": [{"role": "user", "content": "Classify this payment."}]}
  },
  "response": {"status": 200, "headers": {"content-type": "application/json"}, "body": {"choices": []}},
  "live_window": "L1",
  "recorded_at": "2026-09-17T22:00:00+05:30"
}
```

Normalisation drops volatile transport timestamps, authorisation and cookie headers, request,
trace, correlation and idempotency IDs, signatures, nonces, generated multipart boundaries, and
cache-busting query values. It sorts JSON object keys and query keys and removes insignificant
JSON whitespace. It retains provider inputs: models, prompts, array order, media hashes and
business dates embedded in content. Both recorder and fake must hash the same canonical bytes.

---

## Lane B

Owned by B; A edits only the sections above this heading (D23). Frozen at Phase 1 sign-off;
after that, changes need A's OK in chat (LANES.md §2).

B's other two Phase 1 contracts live where the plan puts them:
- **1.4** LLM output schemas: `app/schemas/llm.py` (uses `AnswerChoice` and `PredictionLabel`
  from `app/schemas/common.py`).
- **1.5** Workflow table, role keys per node, and the core → n8n webhook payloads:
  `n8n/README.md` § Workflows, which also records the answer-choice decision.

### 1.6 Screens → read models

One call per screen (plan §7, §12). Every `/app/*` model returns **preformatted ₹ strings per
locale** — the phone never formats a number — plus the raw paise integer for anything it sorts.

#### Merchant app

| Screen | Read model | Writes | Notes |
|---|---|---|---|
| **M0** Language and consent | none (static) | `PUT /app/profile` (role `app`) | Language and consent. Gap G2, accepted. |
| **M1** Home | `GET /app/home` | — | Header band (business name, today's ₹ and count), alert banner (freeze red / notice amber / none), Hisaab card (pending-question count, threshold progress + projected date), tile grid |
| **M2** Confirm payments | `GET /app/questions` | `POST /ledger/claims` (conversation) | The day's selected questions as cards. Gap G1, accepted. |
| **M3** Payments | `GET /app/payments` | — | Filter chips (Today, This week, Needs you, Not a sale), day headers with day totals |
| **M4** Payment detail | `GET /app/payments/{txn}` | "Add a note" → `POST /ledger/claims` (`claim.annotated`) | "What Hisaab recorded": machine label and merchant answer side by side, each dated, each with a tier badge |
| **M5** Case tracker | `GET /app/cases` | — | Stepper, usable balance, plain-words next step. Freeze and tax variants, switched by `case.kind` |
| **M6** Assistant | `GET /assistant/stream` (SSE) | `POST /assistant/inbound` | Not an `/app/*` model; the chat is a stream |
| **M7** Turnover and CA share | `GET /app/turnover` | — | Aggregate by default, two taps to line items; share links for PDF and CSV |

#### Officer app

| Screen | Read model | Writes | Notes |
|---|---|---|---|
| **O1** Queue | `GET /app/officer/queue` | — | Cards by urgency; freezes carry an SLA timer |
| **O2** Case | `GET /app/officer/cases/{id}` | `POST /packs/{id}/approve\|reject` (officer) | Isolation badges, decoy card, tiers, citations with verified flags, sticky Approve bar |
| **O3** Sent and outcomes | `GET /app/officer/outbox` | — | Outbox with SIMULATED stamps and the two timings. Gap G3, accepted. |

#### Presenter and judge views (§12.4)

| Route | Reads |
|---|---|
| `/demo` | `GET /config` for health; writes through `/sim/*` with the admin key |
| `/stage` | Both apps' models, plus `GET /assistant/stream` to stay in sync |
| `/ledger/:id` | `GET /ledger/{m}/entries`, `GET /anchors`, `GET /ledger/verify` |
| `/eval` | `eval/report.json`, served statically |

#### Gaps found in §7: all three accepted by A, 18 Sep

Found by mapping every screen: each was a screen with nothing to call. A owns the endpoint list
(1.3) and is adding all three in one retrofit packet. What A changed is noted under each.

- **G1 — M2 has no read model.** M2 shows the day's selected questions as one card at a time
  (amount, time, payer, channel, question text, "1 of 3"). `/app/home` carries only the *count*.
  **Proposal:** `GET /app/questions?merchant&as_of` returning the open `question.asked` entries,
  each with its credit's display fields and the localized question string. This is on the
  **CP1 critical path** — CP1's second check is "3 Kannada questions arrive in M2".
  **A:** accepted as specified, with the chips typed to `AnswerChoice` rather than free text.
- **G2 — M0 has nowhere to write.** The language choice and the consent need storing, and the
  language drives every later reply. **Proposal:** `PUT /app/profile {language, consent_at}`,
  merchant-app role. Also feeds WF30's language choice.
  **A:** accepted, role `app`. Consent is stored as **ops working state, not a ledger entry**:
  §6's thirteen kinds stay frozen. B agreed, because the plan treats consent as the M0 product
  promise, not as evidence about a credit, and §22 has no consent item. B asked, optionally, for
  `language` and `consent_text_version` to be stored next to `consent_at`.
- **G3 — O3 has no read model.** **Proposal:** `GET /app/officer/outbox` returning sent packs
  with their SIMULATED destination, and the freeze→pack and pack→approval timings.
  **A:** accepted, with the two timings returned as **computed durations**, so the figure on O3
  and the figure printed in the evidence pack cannot drift apart.

---

### 1.7 i18n key list

Rules from plan §8, which every key obeys:

- **Numbers never pass through translation or the LLM.** Keys hold `{slot}` placeholders; core
  fills them with already-formatted strings (`₹4,200`, `₹42.2 L`, `21 Mar, 7:47 PM`).
- Sarvam-Translate **must preserve every `{slot}` verbatim.** The 5.4 generation step rejects a
  translation whose slot set differs from the English source.
- **Languages:** `en` is the source. Generated for the six region languages in
  `sim.catalog` — `kn`, `hi`, `ta`, `te`, `mr`, `bn`. **Kannada and Hindi are reviewed by a
  person** before they ship.
- Kannada runs longer than English. Nothing may truncate at 360 px (§12 quality bar).

Keys are dot-namespaced. English source text shown; `{slot}` values are filled by core.

#### `answer.*` — the one-tap choices (M2 chips, WhatsApp numbered replies)

Decided 18 Sep (see Decisions in `n8n/README.md`): WhatsApp numbers 4, the app shows 5, and
voice or free text can reach all 7 values of `AnswerChoice`.

| Key | English | `AnswerChoice` | Shown on |
|---|---|---|---|
| `answer.sale` | Sale | `sale` | app, WhatsApp |
| `answer.family` | Family | `family` | app, WhatsApp |
| `answer.own_money` | My own money | `own_money` | app, WhatsApp |
| `answer.loan_or_gift` | Loan / other | `loan_or_gift` | app only |
| `answer.not_sure` | Not sure | `not_sure` | app, WhatsApp |
| `answer.numbered_prompt` | Reply {choices} | — | WhatsApp only; `{choices}` = "1 sale · 2 family · 3 my own money · 4 not sure" |

`refund` and `double_payment` have no key: they're never offered as a choice, only recognised
when the merchant says them by voice or in text.

#### `question.*` — what Hisaab asks (M2, WhatsApp)

| Key | English |
|---|---|
| `question.own_money` | {amount} on {when}. Your own money? |
| `question.who_is_payer` | {amount} from {payer} on {when}. Who is this? |
| `question.sale_check` | {amount} from {payer} on {when}. Was this a sale? |
| `question.progress` | {n} of {total} |
| `question.done_for_today` | Done for today. {settled} other payments were settled automatically. |
| `question.why_asking` | I ask so your tax records are right. At most 3 questions a day. |

#### `warning.*` — banners and alerts

| Key | English |
|---|---|
| `warning.freeze_banner` | Payments on hold. We're working on it. |
| `warning.notice_banner` | Tax notice received |
| `warning.threshold_near` | You may cross ₹40 lakh around {date}. You would then need to register for GST. |
| `warning.threshold_crossed` | You crossed ₹40 lakh on {date}. You need to register. |
| `warning.exempt_only` | Your sales are all exempt goods, so you do not need to register. |
| `warning.note_added_later` | Notes added now are marked as added later. |

#### `case.step.*` — M5 stepper (order-tracking style)

| Key | English |
|---|---|
| `case.step.on_hold` | Payments on hold ({time}) |
| `case.step.found` | Disputed payment found ({amount}, {when}) |
| `case.step.pack_ready` | Evidence pack ready |
| `case.step.officer_review` | Paytm officer reviewing |
| `case.step.sent` | Sent to bank and police |
| `case.step.narrowed` | Hold narrowed to {amount} |
| `case.usable_balance` | Usable balance: {amount} |

These never claim innocence (the `no-innocence` guard, §8). They say what happened, not what
it means.

#### `refusal.*`

| Key | English |
|---|---|
| `refusal.hide_income` | I can't help hide income. I can help you keep accurate records. |
| `refusal.generic` | I can't do that. A person from Paytm can help — reply HELP. |

#### `status.*` — replies to `ask_status`

| Key | English |
|---|---|
| `status.handoff` | A person from Paytm will review this. |
| `status.case_open` | Your case is with a Paytm officer. |
| `status.pack_sent` | Your evidence was sent to the bank and police on {date}. |

#### `nav.*` and `action.*` — UI chrome

| Key | English |
|---|---|
| `nav.home` / `nav.payments` / `nav.hisaab` / `nav.assistant` | Home / Payments / Hisaab / Assistant |
| `action.confirm` | Confirm |
| `action.add_note` | Add a note |
| `action.share_ca` | Share with CA |
| `action.approve_send` | Approve and send |
| `action.reject` | Reject |
| `action.escalate` | Escalate |
| `action.also_whatsapp` | Also on WhatsApp |
| `action.hold_to_talk` | Hold to talk |

#### `legal.*` and `brand.*`

| Key | English |
|---|---|
| `brand.prototype_tag` | Prototype · synthetic data |
| `legal.consent` | Hisaab asks at most 3 questions a day. |
| `legal.simulated_stamp` | SIMULATED |

`brand.wordmark` is deliberately **not** a key: "Paytm Hisaab" is set in type and never
translated.
