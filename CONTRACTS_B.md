# Lane B contracts: 1.6 and 1.7

Draft by B, 18 Sep, for Phase 1 sign-off. **Moves into A's `CONTRACTS.md` as B sections once it is
pushed; this file is then deleted.** The other two B contracts live where the plan puts
them: **1.4** in `services/core/app/schemas/llm.py`, **1.5** in `n8n/README.md` (§ Workflows).

Frozen at sign-off; after that, changes need A's OK in chat (LANES.md §2).

---

## 1.6 Screens → read models

One call per screen (plan §7, §12). Every `/app/*` model returns **preformatted ₹ strings per
locale** — the phone never formats a number — plus the raw paise integer for anything it sorts.

### Merchant app

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

### Officer app

| Screen | Read model | Writes | Notes |
|---|---|---|---|
| **O1** Queue | `GET /app/officer/queue` | — | Cards by urgency; freezes carry an SLA timer |
| **O2** Case | `GET /app/officer/cases/{id}` | `POST /packs/{id}/approve\|reject` (officer) | Isolation badges, decoy card, tiers, citations with verified flags, sticky Approve bar |
| **O3** Sent and outcomes | `GET /app/officer/outbox` | — | Outbox with SIMULATED stamps and the two timings. Gap G3, accepted. |

### Presenter and judge views (§12.4)

| Route | Reads |
|---|---|
| `/demo` | `GET /config` for health; writes through `/sim/*` with the admin key |
| `/stage` | Both apps' models, plus `GET /assistant/stream` to stay in sync |
| `/ledger/:id` | `GET /ledger/{m}/entries`, `GET /anchors`, `GET /ledger/verify` |
| `/eval` | `eval/report.json`, served statically |

### Gaps found in §7: all three accepted by A, 18 Sep

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

## 1.7 i18n key list

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

### `answer.*` — the one-tap choices (M2 chips, WhatsApp numbered replies)

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

### `question.*` — what Hisaab asks (M2, WhatsApp)

| Key | English |
|---|---|
| `question.own_money` | {amount} on {when}. Your own money? |
| `question.who_is_payer` | {amount} from {payer} on {when}. Who is this? |
| `question.sale_check` | {amount} from {payer} on {when}. Was this a sale? |
| `question.progress` | {n} of {total} |
| `question.done_for_today` | Done for today. {settled} other payments were settled automatically. |
| `question.why_asking` | I ask so your tax records are right. At most 3 questions a day. |

### `warning.*` — banners and alerts

| Key | English |
|---|---|
| `warning.freeze_banner` | Payments on hold. We're working on it. |
| `warning.notice_banner` | Tax notice received |
| `warning.threshold_near` | You may cross ₹40 lakh around {date}. You would then need to register for GST. |
| `warning.threshold_crossed` | You crossed ₹40 lakh on {date}. You need to register. |
| `warning.exempt_only` | Your sales are all exempt goods, so you do not need to register. |
| `warning.note_added_later` | Notes added now are marked as added later. |

### `case.step.*` — M5 stepper (order-tracking style)

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

### `refusal.*`

| Key | English |
|---|---|
| `refusal.hide_income` | I can't help hide income. I can help you keep accurate records. |
| `refusal.generic` | I can't do that. A person from Paytm can help — reply HELP. |

### `status.*` — replies to `ask_status`

| Key | English |
|---|---|
| `status.handoff` | A person from Paytm will review this. |
| `status.case_open` | Your case is with a Paytm officer. |
| `status.pack_sent` | Your evidence was sent to the bank and police on {date}. |

### `nav.*` and `action.*` — UI chrome

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

### `legal.*` and `brand.*`

| Key | English |
|---|---|
| `brand.prototype_tag` | Prototype · synthetic data |
| `legal.consent` | Hisaab asks at most 3 questions a day. |
| `legal.simulated_stamp` | SIMULATED |

`brand.wordmark` is deliberately **not** a key: "Paytm Hisaab" is set in type and never
translated.
