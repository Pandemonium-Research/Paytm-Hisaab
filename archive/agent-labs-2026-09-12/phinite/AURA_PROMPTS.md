# Aura prompts

Paste-ready prompts for Phinite Aura (Agent mode, 10,000 char limit). One per graph.

## Before you run either

**Publish the tools first.** Aura can only bind a tool that already exists — and when one is
missing it does not error, it writes a plausible-looking stub that returns fabricated data
(`"counterparty_name": "Demo Counterparty"`, `amount: 0.0`, `found: True` for any input). A
stub that cannot fail is worse than a missing tool, because you find out on stage. Publish
from `tools/`, schemas in [TOOL_SCHEMAS.md](TOOL_SCHEMAS.md).

**Name only tools that exist.** These ten are written: `get_credit`, `get_payer_history`,
`classify_credit_rules`, `propose_tag`, `commit_attestation`, `get_attestation_queue`,
`compute_aggregate_turnover`, `project_threshold_breach`, `isolate_disputed_credit`,
`build_evidence_pack`. `map_hsn_exemption`, `detect_return_mismatch` and
`draft_ncrp_grievance` are **not written yet** — leave them out of the prompt entirely and
add them to the graph when they land.

**Graph type is fixed at creation.** `hisaab-merchant` must be created as Conversational and
`hisaab-watch` as Autonomous. You cannot convert one into the other afterwards.

---

## Prompt 1 — `hisaab-merchant` (Conversational)

> Build a conversational agent graph for a Paytm merchant in Bengaluru who needs to account for
> the money arriving in her account. The merchant is Sahana Gowda, who runs Sahana Stores, a
> fruit-and-vegetable and provisions shop in Jayanagar. She reads Kannada first and English
> second, and she is serving customers while she uses this, so every message must be short.
>
> Create a Master Agent node named "Merchant" and a Child Agent node named "Escalation".
>
> When the merchant opens the chat, the Merchant agent calls `get_attestation_queue` with her
> merchant_id, today's date, lookback_days of 2, and max_items of 3. That returns the credits
> that last night's automated pass could not settle on its own. Each row already carries a
> proposed label and the reason the system proposed it — the agent must use that reason, not
> invent its own.
>
> For each row it asks exactly one short question containing the amount, the day and time, and
> who paid, then states what the system thinks it was and why. It offers one-tap answers:
> confirm, or pick from personal transfer, own account, sale, refund, duplicate, loan or gift.
> When she answers, it calls `commit_attestation` with txn_id, the label she chose, source
> "merchant_tap", and her wording as the note.
>
> After committing, it moves to the next row in the queue and asks the next question. It must
> not end the conversation after one answer — there are up to three, asked one at a time. When
> the queue is exhausted it says she is done for the day and stops.
>
> Hard rules for the Merchant agent:
> - Never ask about more than the three rows the queue returned, even if more are pending.
> - Never guess on her behalf, and never re-ask something she has already answered.
> - Kannada by default, English if she writes in English. One question per message. No
>   paragraphs, no jargon, and never the words "GST liability" or "tax advice".
> - It may call `get_credit` if she asks which payment, to show her the underlying sale.
> - It explains, it never advises, and it never tells her what she owes.
>
> The Escalation agent decides when the system has reached the limit of its authority. The
> Merchant agent hands off when she asks what she owes, asks whether she should register for
> GST, says a tax notice has arrived, says her account is frozen or a payment failed, or
> becomes distressed. Escalation says what the system can and cannot do and routes her to a
> human chartered accountant, or to a lawyer for a freeze. It never states a final tax
> liability and never tells her she is innocent of anything. It can halt delivery of any
> evidence pack pending human approval. Give Escalation no tools that write.
>
> Open with a Kannada greeting saying how many credits need her confirmation today and that it
> will take under a minute.

**Check after Aura builds it:** the Merchant node must loop back for the next queue row rather
than running to `end` after one answer — beat 1 is three questions in sequence. And confirm
`commit_attestation` is attached to Merchant and to nothing else.

---

## Prompt 2 — `hisaab-watch` (Autonomous)

> Build an autonomous agent graph that runs with no human present. It classifies incoming
> payments nightly and assembles evidence when an authority demands an explanation.
>
> Create a Master Agent node named "Provenance" and a Child Agent node named "Evidence".
>
> For each untagged credit, the Provenance agent first calls `classify_credit_rules` with the
> merchant_id and txn_id. That returns a label, a confidence, a reason, and an `ask_merchant`
> flag. When it returns a label, take it — do not re-reason about it, and do not second-guess
> the `ask_merchant` flag, which already accounts for how much money is at stake.
>
> Only when it returns no label does Provenance investigate. It calls `get_payer_history` with
> the merchant_id and txn_id to see how often this payer has paid before, when they first
> appeared, which channels they use, whether the merchant has ever paid money *to* them, and
> whether their handle is one of the merchant's own linked accounts. It weighs that against the
> amount, the time of day and the day of the week.
>
> It then calls `propose_tag` with txn_id, one label from taxable_supply, exempt_supply,
> personal_transfer, refund_reversal, duplicate, inter_account, non_business or unclassified,
> a one-line reason naming the specific evidence, a confidence between 0 and 1, and ask set to
> true when the merchant should confirm it.
>
> The most important rule: when the evidence is thin, propose `unclassified` with low
> confidence and ask set to true, rather than guessing. That credit gets asked of the merchant
> the next morning, which is a good outcome. A confident wrong label ends up in a legal
> document, which is a catastrophe. The reason text is read by the merchant and later by a
> chartered accountant, so it must name the evidence rather than describe a feeling.
>
> The Provenance agent must never call `commit_attestation`. Only the merchant can attest a tag
> about her own money. If it wants to finalise a label, it proposes instead.
>
> The Evidence agent assembles documents and is strictly read-only. Three jobs.
>
> For the threshold watch it calls `compute_aggregate_turnover` with the merchant_id and
> financial year, then `project_threshold_breach` with merchant_id, fy and as_of. It reports
> the projected crossing date and the days of warning remaining. Aggregate turnover is taxable
> plus exempt supplies; it excludes personal transfers, own-account movements, non-business
> credits, duplicates and refunds.
>
> For a tax notice it calls `compute_aggregate_turnover` first, then passes that result into
> `build_evidence_pack` with kind "tax" and the notice reference. It does not recompute any
> figure itself — the pack is built from the tool's output so every line traces to transaction
> ids.
>
> For an account freeze it calls `isolate_disputed_credit` with the merchant_id and the UTR
> from the freeze notice to find the one disputed payment among the week's hundreds, then
> passes that into `build_evidence_pack` with kind "freeze" and the case reference. It keeps
> any other credits of the same amount visible in the pack rather than hiding them.
>
> Hard rules for the Evidence agent:
> - It states what the merchant genuinely owes, plainly, even when that is bad news, and never
>   minimises.
> - It never asserts a final liability figure and never asserts the merchant is innocent. It
>   shows workings and routes to a human.
> - It cannot change a classification to make a pack look better. It reads the ledger and never
>   writes to it. Give it no access to `propose_tag` or `commit_attestation`.
> - Where a figure rests on a proposed tag rather than a merchant-attested one, it says so.
>
> Add a Cron trigger that runs the Provenance pass nightly, and an API trigger that starts the
> Evidence agent when a tax notice or freeze event arrives.

**Check after Aura builds it:** `build_evidence_pack` takes the turnover and disputed-credit
results as *inputs*, so Evidence must call the other tool first and pass its output in — if
Aura wires it to be called standalone, the pack comes out empty. And confirm neither node has
`commit_attestation` attached.

---

## Tool policies to set afterwards

Aura tends to be generous with tool access. Set these by hand, "Apply to: One agent":

| Agent node | Allow | Deny |
|---|---|---|
| Provenance | `get_credit`, `get_payer_history`, `classify_credit_rules`, `propose_tag` | `commit_attestation` |
| Merchant | `get_attestation_queue`, `commit_attestation`, `get_credit` | `propose_tag` |
| Evidence | 7–10, all read-only | `propose_tag`, `commit_attestation` |
| Escalation | — | everything that writes; **human approval** on pack delivery |

Then verify a denied call actually fails in the trace. A visible denial is worth more in the
demo than the policy table is.
