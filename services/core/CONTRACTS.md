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
