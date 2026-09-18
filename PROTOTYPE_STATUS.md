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
| A | Persistent clock, rails ingestion/replay and merchant/credit reads | Starting |
| A | Real proposals, questions, claims and derived current view | Next |
| A | Rules, question selection, M1/M2 read models and app-message forwarding | Next |
| A | Repeatable demo seed/reset and first-gate integration check | Next |
| B | Pull `e499483`; build minimal WF10, including the hard-case Sarvam branch | Ready |
| B | M1 Home and M2 Confirm; app taps through WF31; minimal language selection | Ready |
| Both | Run first gate on local n8n/core/fakes, then validate the real-provider path | Pending |

## Second gate: freeze and approval

Lien event → case → isolate disputed payment and show decoy → evidence pack → officer approves
→ simulated outbox delivery → merchant case tracker updates.

| Owner | Work | Status |
|---|---|---|
| A | Case creation, isolation, pack, approve/reject/send and case read models | After first gate |
| B | WF20, O1/O2 and M5 | After first gate |
| Both | Officer approval and simulated send end to end | Pending |

Then add turnover/threshold and the notice report. A selected specimen notice can precede OCR.

## Delivered

- H2–H4: local stack, contract-complete stubs, basic chat/Twilio fakes and cassette recording.
- B: WF30 and WF31's signed numbered-reply path work against the fixtures (`e5b25ab`).
- A: database roles/migrations, chain append/verify and mutation controls (`e499483`).
- A: B's local n8n environment settings and workflow import/export task commands.
- Latest validation: 198 core, 26 real Postgres and 19 fakes tests; running-core chain smoke
  and HTTPS health check passed.

**Current limitation:** the product HTTP routes still return fixtures. A successful fixture
acknowledgement does not persist evidence. Replace these routes before calling the first gate done.

## Deferred until the two gates work

Voice/TTS, Cognee enrichment, generated translations, additional languages, M6, Cloud migration,
full-year workflow seeding, anchors and tamper presentation, comprehensive security matrices,
additional legal research/guards, evaluations, extra screens and visual polish. Keep existing
controls, input validation, approval before sending, synthetic/simulated labels and fake/live
separation. Local n8n is the initial target; Cloud `$env` is still unresolved for B's S5/S8 checks.

## Working rules

- Keep lane ownership and existing request/response contracts.
- Commit and push completed slices; update this file and A's own phase checkboxes with evidence.
- No Codex or Claude coauthor trailers. No history rewrite is part of this queue.
- Test behavior that can break the two gates; do not add unrelated hardening as a prerequisite.
