# Functioning prototype: current scope and status

Updated 18 September 2026. This is the active build queue; the larger phase plan remains a
backlog. The user has prioritized working behavior over additional security, legal research,
measurement and polish.

## First gate: payments and answers

Load visible demo payments → WF10 classifies and saves proposals → select up to three questions
→ show them in M2 and send through WF30 → WhatsApp replies and app taps save merchant answers.
Machine labels remain visible alongside those answers. Answers survive a service restart.

| Owner | Next work | Status |
|---|---|---|
| A | Persistent clock, rails ingestion/replay and merchant/credit reads | Complete |
| A | Real proposals, questions, claims and derived current view | Complete |
| A | Rules, question selection, M1/M2 reads and language preference | Complete |
| A | App-message forwarding and persisted assistant delivery | Complete; live workflow smoke pending |
| A | Repeatable demo seed/reset and first-gate integration check | Next |
| B | Minimal WF10, including the hard-case Sarvam branch | Built/imported locally (`6152c98`); real integration pending |
| B | M1 Home and M2 Confirm; app taps through WF31; minimal language selection | Built/running locally (`6152c98`); real integration pending |
| Both | Run first gate on local n8n/core/fakes, then validate the real-provider path | Pending |

## Second gate: freeze and approval

Lien event → case → isolate disputed payment and show decoy → evidence pack → officer approves
→ simulated outbox delivery → merchant case tracker updates.

| Owner | Work | Status |
|---|---|---|
| A | Case creation, isolation, pack, approve/reject/send and case read models | After first gate |
| B | WF20, O1/O2 and M5 | Prepared locally against existing contracts; approval/rejection orchestration checks pass; H8/CP2 pending |
| Both | Officer approval and simulated send end to end | Pending |

Then add turnover/threshold and the notice report. A selected specimen notice can precede OCR.

## Delivered

- H2–H4: local stack, contract-complete stubs, basic chat/Twilio fakes and cassette recording.
- B: WF30 and WF31's signed numbered-reply path work against the fixtures (`e5b25ab`).
- A: database roles/migrations, chain append/verify and mutation controls (`e499483`).
- A: B's local n8n environment settings and workflow import/export task commands.
- A: Phase 4 payment backend now persists rails, proposals, questions and merchant answers.
  M1/M2 and payment/history reads use Postgres; preferred language is saved.
- A: assistant inbound forwards unchanged JSON to B's WF31; WF30 app messages persist in
  `ops.conversations`. A failed workflow connection returns 502 instead of fixture success.
- Running-core smoke: a saved family answer closes the question, retains its machine label
  and survives a core restart. The generated 68-credit window selects exactly the expected
  ₹7,500, ₹4,850 and ₹15,000 payments; ₹23 is skipped and Raghu has two prior purchases.
- Validation: 173 core, 35 Postgres and 19 fakes tests passed. The real container replay
  loaded 37,054 transactions and one event through 10 March 2026 at 02:00 IST.
- `python tasks.py replay --split demo --until 2026-03-10T02:00:00+05:30` loads visible
  records only; repeating it does not duplicate source records or observed-credit evidence.

**Current limitation:** assistant SSE, case processing, evidence packs, officer
approvals, turnover/threshold and reset still return fixtures. The first gate remains open until
B's WF10/screens and the shared app/WhatsApp path run against the real backend. Persisting raw
rails events does not yet open cases or process a freeze.

### Integration notes for B

- B's `6152c98` supplies the app envelope and uses the demo clock for WhatsApp replies.
  A forwards unchanged `AssistantInboundRequest` JSON to `/webhook/hisaab/wf31-assistant`
  with `X-N8N-Webhook-Secret`; app taps carry explicit question identity in `text`.
- Ledger response hashes use hexadecimal strings; the stored/internal digests remain 32 bytes.
- The demo merchant is `MID_DEMO_SAHANA`. Fetch its language and current time from real reads.
  Keep WF10's lookback at 8–9 March for the ordinary Tuesday check. Rules use stored payment
  features; shared-surname QR payments need confirmation even when the payer has prior credits.
- Question IDs must stay the same on retries. Both selection and question writes enforce
  three per merchant per business day; answers preserve the machine label.
- `GET /config` is real; prompts and other unlisted skills remain fixtures.

B's first-gate runner is ready:
`python n8n/tests/check_first_gate.py --merchant MID_DEMO_SAHANA --restart-core`.
Use `/?merchant=MID_DEMO_SAHANA` for B's web app; its current default merchant is
`MID_DEMO_BLR`, which is absent from generated demo data. WF10 currently processes all
unlabelled history; B must limit classification/question candidates to the ordinary Tuesday
window (8–9 Mar) or classify prior history separately before this checkpoint.
No joint gate is marked passed.
The exact WF31 app envelope and WF20 status/approval handoffs are in `n8n/README.md`.

## Deferred until the two gates work

Voice/TTS, Cognee enrichment, generated translations, additional languages, M6/assistant SSE, Cloud migration,
full-year workflow seeding, anchors and tamper presentation, comprehensive security matrices,
additional legal research/guards, evaluations, extra screens and visual polish. Keep existing
controls, input validation, approval before sending, synthetic/simulated labels and fake/live
separation. Local n8n is the initial target; Cloud `$env` is still unresolved for B's S5/S8 checks.

## Working rules

- Keep lane ownership and existing request/response contracts.
- Commit and push completed slices; update this file and A's own phase checkboxes with evidence.
- No Codex or Claude coauthor trailers. No history rewrite is part of this queue.
- Test behavior that can break the two gates; do not add unrelated hardening as a prerequisite.
