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
| A | App-message forwarding and persisted assistant delivery | Complete; real local WF31/WF30 smoke passed |
| A | Repeatable demo snapshot/reset | Complete; `snapshot` 4 s, `reset` 36 s, verified round trip |
| A | Credit window on `GET /credits` so WF10 stops paging the whole history | Complete (`deb9ba1`); 61 calls/108.8 s -> 1 call/2.3 s |
| A | Freeze detector (6.9) | Complete; the lien opens `CASE-FREEZE-<event>` and WF20 is told after commit |
| A | Approvals and the outbox gate (6.10) | Complete; the gate reads the ledger, decisions are final, sends are simulated |
| A | Four case/officer read models (6.11 prototype scope) | Complete; Composer 2.5 implementation, A review/fixes, Postgres and HTTP checks |
| A | Payment isolation (6.4) and real freeze packs/PDF (6.8) | Complete in prototype freeze scope; actual artifacts and isolated HTTP lifecycle verified |
| B | Minimal WF10, including the hard-case Sarvam branch | Complete; passes against the real stack |
| B | M1 Home and M2 Confirm; app taps through WF31; minimal language selection | Complete; real reads and persisted taps |
| Both | Run first gate on local n8n/core/fakes, then validate the real-provider path | **Passes cold on B's machine** (117 s); A's machine is ~10x slower and timed out. Awaiting a re-run on A's with the credit window. Real-provider path (L1) pending |

## Second gate: freeze and approval

Lien event → case → isolate disputed payment and show decoy → evidence pack → officer approves
→ simulated outbox delivery → merchant case tracker updates.

| Owner | Work | Status |
|---|---|---|
| A | Case creation, isolation, pack, approve/reject/send and case read models | Complete in prototype freeze scope; minimal H8 core handoff ready |
| B | WF20, O1/O2 and M5 | Prepared locally; connect the real pack handoff, bound the polling loop and run CP2 |
| Both | Officer approval and simulated send end to end | Core HTTP lifecycle passes; joint n8n, officer-screen and merchant-tracker check pending |

Then add turnover/threshold and the notice report. A selected specimen notice can precede OCR.

## Delivered

- H2–H4: local stack, contract-complete stubs, basic chat/Twilio fakes and cassette recording.
- B: WF30 and WF31's signed numbered-reply path work against the fixtures (`e5b25ab`).
- A: database roles/migrations, chain append/verify and mutation controls (`e499483`).
- A: B's local n8n environment settings and workflow import/export task commands.
- A (`732a65d`): Phase 4 payment backend now persists rails, proposals, questions and merchant answers.
  M1/M2 and payment/history reads use Postgres; preferred language is saved.
- A: assistant inbound forwards unchanged JSON to B's WF31; WF30 app messages persist in
  `ops.conversations`. A failed workflow connection returns 502 instead of fixture success.
- Real local workflow smoke passed: app tap → core forwarding → B's WF31 → persisted
  family answer → WF30 → persisted Kannada acknowledgement (`ನಿಮ್ಮ ಉತ್ತರ ದಾಖಲಾಗಿದೆ.`).
  It used a separate synthetic merchant, leaving the demo window available for B's WF10.
- Running-core smoke: a saved family answer closes the question, retains its machine label
  and survives a core restart. The generated 68-credit window selects exactly the expected
  ₹7,500, ₹4,850 and ₹15,000 payments; ₹23 is skipped and Raghu has two prior purchases.
- Validation: 173 core, 35 Postgres and 19 fakes tests passed. The real container replay
  loaded 37,054 transactions and one event through 10 March 2026 at 02:00 IST.
- `python tasks.py replay --split demo --until 2026-03-10T02:00:00+05:30` loads visible
  records only; repeating it does not duplicate source records or observed-credit evidence.

- **B: CP1 passes cold, in one invocation (18 Sep).** From an empty database restored by
  `tasks.py reset` (0 proposals, 0 questions), a single `check_first_gate --restart-core` run
  finished in **132 s wall, WF10 itself 117.4 s**, and reported three *new* questions. A's run on a
  smaller machine took 1220 s and died on n8n's pg-pool and JS task runner, so the 180 s wait is
  now `--timeout`, default 1800 s: interrupting WF10 part-labels the window, and because WF10 skips
  labelled credits the database can never select three questions again without `tasks.py reset`.
  The gate also asserts WF10's own execution succeeded — an earlier "pass" of mine sat on questions
  from a previous run while that invocation's WF10 had failed at `Read credits`, and nothing noticed.
  An empty body no longer starts a run (it now errors in 0.1 s); probing whether the webhook had
  registered used to classify a whole window.
- **B (first gate, 18 Sep): CP1 passes end to end against the real backend.** One WF10 run over
  the 8–9 March IST window wrote 68 `label.proposed` entries and selected three questions; the
  Kannada text appears in both the fakes' WhatsApp outbox and M2's real read model; two app taps
  and one signed WhatsApp numbered reply persisted `own_money`, `family` and `sale`, matching the
  seeded answer key; the machine proposals are unchanged, `GET /ledger/verify` returns ok, and the
  answers survive a core restart. A numbered reply stands in for the voice answer (H5 deferred)
  and memory recall is deferred, so that one CP1 line stays open.
- B: `python n8n/tests/run_local.py` covers the window boundaries offline: a credit just before
  the window and one exactly at its end are both excluded.

- **A: `tasks.py snapshot` / `tasks.py reset` (18 Sep).** `snapshot` dumps the demo database in
  about 4 s (4.8 MB); `reset` restores it in about 36 s, inside the plan's 60 s budget. Verified by
  round trip: a proposal written after the snapshot is gone after the reset, and the restored
  database keeps both append-only triggers, `hisaab_app`'s insert-only grants, `ledger.current_view`
  and the sim clock. `GET /ledger/verify` returns ok afterwards, and an owner `UPDATE` is still
  refused by the trigger. Take the snapshot straight after `replay`, before any workflow run (D33).
- **A: approvals and the outbox gate, 6.10 (18 Sep, D37, D38).** `POST /packs/{id}/approve|reject`
  and `POST /outbox/{pack}/send` are real. The gate reads `pack.approved`/`pack.rejected` from the
  ledger, never the `ops.approvals` status column, which the application role can edit; a pack gets
  one final decision; sends are simulated, idempotent and never touch the network. The waiting
  workflow is resumed after commit, only at our own n8n. On the running stack, send before approval
  was 409, approval with the evidence key 403, officer approval 200, reject afterwards 409, and send
  simulated; a probe standing in for WF20's Wait found the decision already committed when resumed.
  61 Postgres tests at this checkpoint; eight deliberate breakages of the gate each fail one.
  The real `POST /packs` build now uses this recording half (`record_pack`), delivered in 6.8 below.

- **A: freeze detector, 6.9 (18 Sep, D35, D36).** A `lien_marked` event opens
  `case.opened(freeze)` as `CASE-FREEZE-<event_id>`, dated to the lien, and `POST /rails/events`
  returns the real `opened_case_ids`. A burst of 3 or more declines in the 30 minutes up to the lien
  is recorded on the case; declines alone open nothing, and a late lien does not count the declines
  it caused. WF20 is POSTed only after the case commits, best effort; replay opens the case without
  calling WF20. On the running stack, a probe standing in for WF20 found the case already committed
  when notified, and with n8n stopped the lien still opened its case. 47 Postgres tests; five
  deliberate breakages of the detector each fail a test. **An earlier draft had the race it was
  meant to prevent:** FastAPI 0.141 runs background tasks before a yield dependency exits, so the
  webhook would have fired before COMMIT. Found by checking the order rather than assuming it, and
  fixed with `scope="function"` on that route's connection.

- **A: case/officer reads, 6.11 prototype scope (18 Sep).** The four merchant-case, officer-queue,
  case-detail and outbox routes read Postgres at the sim clock, including rewind. Officer statuses
  follow the ledger; tiers and weak share use the recorded pack; real delivery timestamps yield
  real elapsed seconds. Detail verifies the chain on every request. No PDF exists until one is
  recorded, and sending a pack does not claim the bank released the hold. Composer 2.5 built from
  A's spec; A corrected and validated it: 166 core, 73 distinct Postgres and 19 fakes checks pass.
  Running core returns empty demo case lists and unknown-case 404; a separate HTTP lifecycle on
  the isolated test database passed open → awaiting approval → approved → sent → rewind. Test data
  was rolled back and the shared demo clock was untouched. `/app/turnover` remains deferred to 6.2.
- Cursor's read-only review of 6.9/6.10 found no blocker in their implemented flows. Its known
  fixture-pack integration gap is now closed by the real 6.8 build.
- **A: isolation and freeze evidence packs, 6.4/6.8 prototype scope (18 Sep).** Independent UTR
  and amount/date matching returns the actual disputed credit, same-amount decoy, recorded bill,
  terminal/geo and seven-day count. `POST /cases` persists cases; `POST /packs` writes actual JSON
  and an English ReportLab PDF, records its SHA-256 and returns the original build on retry.
  Officer-authenticated artifact downloads follow the sim clock. Grading covers the selected
  disputed payment only; full-period tiers, notice PDFs and Indic rendering remain deferred.
  Composer built from A's spec; A reviewed, corrected and verified the result. Validation:
  **163 core, 88 Postgres and 19 fakes tests pass.** An isolated real HTTP run found `DM0038619`
  by both badges, one decoy and 339 seven-day credits, then built → approved → sent with a valid
  chain. Unapproved send was 409, missing artifact key 403 and rewind download 404. Both PDF
  pages were rendered and inspected. Test data was rolled back; the shared CP1 clock/data stayed
  unchanged. Core was rebuilt with the new dependency; the joint WF20/screens check is still pending.

- **A: half-open credit window on `GET /credits` (18 Sep, D34).** `from` and `to` are optional
  aware instants bounding `[from, to)` on the payment's `ts`: `from` is inclusive, `to` exclusive,
  either may be given alone, `as_of` still caps the page, and paging works inside the window. A
  bare date is refused, because the chain stores UTC and the screens answer IST. Verified by 36
  Postgres tests covering both edges, the same instant written as `+05:30` and as `Z` selecting
  the same payments, a cursor that stays inside its window, a window that cannot outrun business
  time, and 422 for a backwards or unzoned bound. This is B's requested fix for A's WF10 failure:
  the run was paging all 12,097 credits through a Code node to keep 68, so every page was a
  task-runner job over a large payload. WF10 can now ask for the window in one call.
  Measured against the running stack: paging the whole history is **61 calls, 12,097 credits,
  108.8 s** to keep 68; the same window is **1 call, 68 credits, 2.3 s** — 46x. That 108.8 s is
  on its own very nearly B's whole successful run (117.4 s), before a single credit is
  classified, which is most of the gap between the two machines.

- **B answered A's CP1 question (18 Sep, `26d6e9b`): CP1 does reproduce, and A's reading of the
  resumed run was right.** B's passing run did print `(resumed run: ...)`, and its WF10 execution
  had in fact errored in 4.7 s at Read credits; the gate still printed PASS because three
  questions from an earlier run were already there. Classification had nonetheless completed in a
  single cold invocation on B's machine (execution 60, success in 111.9 s), and a fresh cold run
  from empty volumes after `tasks.py reset` succeeded in 117.4 s, 132 s for the whole gate. B saw
  no `pg-pool` or task-runner errors and has 15.5 GiB for Docker, so the same workload takes
  roughly ten times as long on A's machine. B's fixes: `--timeout` defaulting to 1800 s in place
  of the hard 180 s, an assertion that WF10's own execution succeeded (read from n8n's database,
  printed as `WF10 execution: success in 117.4s`), and an empty webhook body that now errors in
  0.1 s instead of classifying a whole window, closing the footgun that poisoned A's database.

- **A could not reproduce CP1 (18 Sep).** On a cold database (zero proposals, zero questions) the
  WF10 run did not finish inside `check_first_gate.py`'s 180 s wait. Two n8n executions ended at
  1220 s (error) and 1632 s (cancelled), with `pg-pool` `timeout exceeded when trying to connect`
  and `Your Code node task was not matched to a runner within the timeout period (waited 128
  seconds)`. n8n and core share one Postgres, and WF10 makes roughly 300 serial HTTP calls per run.
  One of those runs was A's own accidental second trigger, which doubled the load; the capacity
  limit is real either way. **The trap this exposed:** the interrupted run left 67 of the window's
  68 credits labelled, and WF10 skips labelled credits, so that database could never again select
  three questions. That is what made reset the blocker. Open question for B: did the passing run
  print `(resumed run: the questions already existed...)`, and how long did its WF10 execution take?

**Current limitation:** assistant SSE, full-period tiers, turnover/threshold/escalation skills
and `/app/turnover` remain unfinished. Freeze packs grade only the selected disputed payment and
use English PDFs; notice pack builds return 422 until their report is implemented. The first
gate passes on B's local stack; the real-provider check is pending. The freeze backend now works
through actual case, isolation, pack, officer decision, simulated delivery and read models.
CP2 still needs its joint workflow and screen check.

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
- `GET /credits` accepts `from` and `to`: a half-open `[from, to)` window on the payment's `ts`,
  both aware instants (a bare date is refused). WF10 should pass its `window_from`/`window_to`
  straight through instead of paging and filtering in the Code node. `services/core/CONTRACTS.md`
  has the full semantics.
- A lien opens a real case and core POSTs WF20's `{case_id, merchant_id, opened_at, trigger}` after
  commit; `services/core/CONTRACTS.md` shows the body. Isolation and `POST /packs` now return real
  evidence and pack IDs. B should bound WF20's 5 s polling loop, then run a controlled local CP2
  with O1/O2 and M5. n8n remains stopped on A's stack until that integration run.
- Pack responses expose `/api/packs/<opaque-id>.json` and `.pdf`; downloads require the officer
  role header, already supported by the web download helper. Tier amounts describe the selected
  disputed payment, not the merchant's full-period evidence coverage.
- Approve/reject/send are real (`services/core/CONTRACTS.md` has the semantics). WF20's send is gated
  in core on the ledger, and `workflow_resumed: true` now means a resume is scheduled after commit.
  The frozen `BuildPackRequest` has no resume URL field. Polling uses the real officer-case status;
  HTTP resume registration remains a separate integration decision. Stored resume URLs must be
  on `N8N_BASE_URL`'s origin. Known limit, not addressed: WF20 holds the
  officer key for its send, so that key could also approve. The human's approval is enforced as
  "an officer-role entry", not as "a person".
- `GET /config` is real; prompts and other unlisted skills remain fixtures.
- `tasks.py import-n8n --target local --activate` fills missing local environment values from
  `.env.example`. This keeps imported credentials aligned with core's fake defaults, even
  when an existing `.env` predates the role keys. Cloud import still requires explicit live mode.
- The web app is built and served at `http://localhost:8080/?merchant=MID_DEMO_SAHANA`;
  its real Home API reports the persisted business date and balance. No demo questions are
  prefilled: WF10 must create them during CP1.

B's first-gate runner passes:
`python n8n/tests/check_first_gate.py --merchant MID_DEMO_SAHANA --restart-core`.
Both defaults now point at `MID_DEMO_SAHANA`, and WF10 no longer processes all unlabelled
history: classification is limited to a half-open IST window (`window_from`/`window_to`,
default the two days before the `as_of` IST day start), so one run labels exactly the 68
credits of 8–9 March. `python n8n/tests/prepare_cp1.py` mounts the visible demo and replays
to 10 Mar 02:00 IST first; both commands are idempotent.
**The first gate is marked passed** (see Delivered). The second gate is not.
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
- Give Cursor one helper or endpoint per build job, with exact inputs, outputs and acceptance
  checks. A reviews and validates each result before assigning dependent work; A runs commands
  that Cursor's approval settings block.
