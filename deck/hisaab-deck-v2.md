# Paytm Hisaab — deck v2

For **Paytm Build for India, 19 September 2026, Track 3: Autonomous AI Teammates**.

Round 1 requires: Title, Problem Statement, Proposed Solution, Tech Stack, USP, Impact &
Benefits, Business Model. The last one is missing from v1 entirely.

---

## What changed from v1, and why

| Change | Reason |
|---|---|
| Freeze leads, tax follows | The buildathon judges validated the cybercrime half and pushed back on the tax half. Lead with the case where the merchant is unambiguously blameless. |
| The 2026 SOP and the High Court rulings become the spine | Between January and August 2026 the law started requiring exactly the artefact you produce. This is the strongest material you have and v1 mentions it in one passing line on slide 12. |
| Personal and family money removed from every slide | "It's the merchant's own fault for taking personal money on the shop QR" is the objection you already got. Don't invite it again. The vegetable vendor's tax problem doesn't involve it. |
| New: provenance and tamper-evidence slide | Answers three objections with one mechanism. |
| New: evidence tiering slide | The most convincing thing you can add before the 19th. |
| New: delivery channel slide | v1's weakest link is "the merchant or their CA files it." |
| New: business model slide | Required by Round 1, absent from v1. |
| Tech stack rebuilt | Phinite isn't a sponsor this time. n8n and Sarvam are. |

---

## Slide 1 — Title

**Paytm Hisaab**
*Every rupee, on your side.*

The autonomous teammate that accounts for a merchant's money when an authority
demands an explanation, and answers on their behalf inside the deadline.

Build for India · Track 3: Autonomous AI Teammates · 19 September 2026

> If any judge overlaps with the Phinite buildathon, add one line: *Built on feedback from the
> Agent Labs Buildathon, where we were told the tagging exists and the commingling is the
> merchant's own problem. We agreed, cut both, and rebuilt around the part that held.*
> Say it openly or not at all.

---

## Slide 2 — Problem: 09:30 on a Tuesday

Her payments start declining. No message, no reason, no reference number.

She sold someone 12 kg of onions. That customer was three layers downstream of a fraud
victim in another state. She is not named in the FIR. Three hundred and thirty-nine payments
came into her account that week and she cannot tell you which one is the problem.

Her supplier payment is due today.

**The whole account is held for a ₹4,200 dispute.**

---

## Slide 3 — The law changed in 2026, and created a duty nobody can discharge

**MHA / I4C SOP, notified 2 January 2026**
- Lien on the disputed amount is the default **where that amount is identifiable**
- Disputed sums under ₹50,000 can be settled without a court order **if the trail is verified**
- Authorities must distinguish **money mules from bona fide receivers** who sold real goods

**Andhra Pradesh HC, July 2026** — a merchant's account cannot be frozen merely for receiving
UPI payments from a fraud accused.

**Rajasthan HC, August 2026** (*Balaji Enterprises v RBI*) — statewide directions. Labels like
"suspicious transaction", "mule account" or "Layer-1 account" are not by themselves reasons to
immobilise an account. Where the amount is identifiable, hold only that amount.

> Every one of those conditions needs someone to identify the payment, verify the trail, and
> tell a shopkeeper from a mule.
>
> The bank has no bill. The investigating officer is in another state and has never seen the
> shop. She has no lawyer.
>
> **Paytm has the bill, the device, the location and both sides of the payment.**

---

## Slide 4 — The same ledger, the slower authority

The tax department compares UPI collections against filed returns and bills the difference.

**Haveri, 2025.** A vegetable vendor. Vegetables are exempt from GST. Four years of credits
added up and billed as income: **₹29 lakh**. Within weeks, "No UPI, cash only" on shutters
across Karnataka.

**Still live.** CAclubindia, 2 September 2026: August 2026 notices covered *differences in
turnover* and *exemption claims*, among others.

He did nothing wrong. There is no version of that story where it is his fault. The department
counted gross credits and called it turnover.

**What it costs Paytm:** a frozen merchant stops transacting that morning. A frightened one
takes the QR down for good. Dead Soundbox, zero GMV, no lending origination.

---

## Slide 5 — Solution: one ledger, two readers

**Provenance ledger** — a label on every incoming credit, recorded with the date it was made
and locked.

Two downstream reads, not two products:
- **The disputed rupee** → freeze response, NCRP/CFCFRMS grievance
- **Defensible turnover** → threshold watch, notice response

**The engine.** Eight labels. 98.6% are ordinary sales, settled by deterministic rules. The
agent reasons only about the 1.4% that need judgement.

**Budget: at most three questions a day.** Over a simulated year: 189 questions, median 1.3 a
day. Manual tagging of every payment is not humanly possible and would be its own attack
surface. Ask more than three and the product is dead.

> Present the labels as a quiet list. Do **not** put personal or own-account money in a
> headline, a pie chart, or a callout.

---

## Slide 6 — Why this record cannot be manufactured

The value of the record is *when* it was made, not what it says. Anyone can type a history
after the freeze arrives.

- **The machine's label is never removed.** Where the rules can't decide, it stays `unknown`
  and the merchant is asked. Her answer is added **alongside**, marked as her own claim. She
  cannot overwrite it.
- **She can add a correction to any payment**, and that too is marked as her claim, with the
  date she made it.
- **The ledger is append-only and chained.** Every entry carries the moment it was recorded.
  Nothing can be backdated without breaking the chain.

This answers three questions at once:

| Objection | Answer |
|---|---|
| Paytm already tags transactions | That is the consumer app, on money going out, with budgeting labels. Rewritable, and never built to be shown to anyone outside Paytm. |
| The merchant could just lie | She can. The document says she said it, and says when. She hasn't laundered a claim into machine output. |
| A real mule could use this | Not retroactively. The history has to already exist, and it has to be mostly bill-backed. |

---

## Slide 7 — The pack says how much it is worth

Not every line in an evidence pack carries the same weight, and a document that pretends
otherwise is the one an officer distrusts.

Four levels, **totalled separately**:

1. **Backed by a bill** — items, till, minute
2. **Derived by rule** — from the payment's own characteristics
3. **Stated when asked** — she answered the system's question that day
4. **Added later** — her own annotation, with how long after the payment, and whether before
   or after the notice arrived

A genuine shop's pack is mostly levels 1 and 2. A fabricated one is mostly levels 3 and 4.
**The shape of the document does the sorting.**

This makes the pack more persuasive, not less, because it stops overclaiming. It is also the
honest answer to "what if the merchant is the criminal": we sort, we don't advocate.

---

## Slide 8 — The teammate (Track 3)

**Autonomously, every night:** classifies the day's credits, queues only what it genuinely
cannot settle, watches the threshold.

**The moment payments start declining:** detects the freeze, isolates the disputed credit by
UTR and independently by amount and date, pulls the bill behind it, assembles the pack,
drafts the grievance citing the SOP and the judgments, routes it.

**Stops and hands to a human** when the evidence doesn't support release, when the amount is
large, or when it is anything other than an ordinary goods sale. Escalation holds every pack
for approval before it leaves.

**The outcome it is measured on:**
- time from lien to proportionate release
- share of the merchant's balance kept operable while the case runs
- share of merchants still transacting 30 days after a freeze

---

## Slide 9 — Delivery: Paytm is the channel

v1's output was a document handed to the merchant to send somewhere. That is the weak link.
Representations to bank nodal officers routinely go unanswered for months.

Paytm is not a stranger to them. It is the regulated PSP, already in the CFCFRMS loop, already
answering bank and law-enforcement requests as part of its normal operations.

So the shape is two-sided:

- **She attests.** Her phone, her language, one tap, three questions a day.
- **Paytm answers.** On the channel that already reaches the bank and the investigating
  officer, within the time limits the SOP sets.

When police ask about a suspect payment, Paytm answers and the merchant is not told. That is
correct, and it is how every bank already works. Warning a genuine mule is the worst possible
outcome.

---

## Slide 10 — What the merchant sees

*(existing dashboard mock)*

**Default view is the aggregate.** How much of her money counts as turnover, how close she is
to the threshold, what the packs say. That is all she needs day to day.

**The detail is two taps away and exportable.** When the envelope arrives she takes it to a GST
practitioner or the accountant the shops on that street use. That person has never seen this
product, has an hour, and needs the line items. The export has to explain itself to someone
arriving cold.

The same agent runs on WhatsApp, where she actually is.

---

## Slide 11 — Demo: the emergency

Frozen at 09:30, 24 March. 339 payments came in that week.

**The agent isolates it.** ₹4,200 on 21 March at 19:47, till POS01. Matched by UTR and
independently by amount and date. The sale record comes with it: the bill, the items, the till,
the minute.

**And the decoy it did not choose.** A second ₹4,200 that same week from a regular customer,
listed in the pack and explicitly not named as the disputed one. Only the date separates them.

Then it drafts the NCRP/CFCFRMS grievance, citing the SOP's lien-only default and the
judgments behind it.

**It never asserts she is innocent.** Some frozen accounts genuinely are mule accounts. It
assembles evidence; a human decides.

---

## Slide 12 — Demo: the ordinary Tuesday, and the notice

**Before anything went wrong.** Thirty-nine credits over the weekend. The agent asks about
three, in Kannada, one line each. Thirty-six settle silently. A ₹23 payment nobody can place is
left alone. That is the record the previous slide was built from.

**31 January.** "At your current rate you cross ₹40 lakh around 14 March. You will need to
register." Forty-three days of warning, computed.

**The notice, claiming ₹60.98L.** Aggregate turnover ₹42.2L, within 1.6% of truth. Exempt
₹31.3L. Taxable ₹10.9L. ₹18.8L that is not turnover, every line traced.

And it says plainly: the claim is wrong, **and you did cross ₹40 lakh. You must register.**

---

## Slide 13 — What we can prove

One merchant, one year, 13,267 credits, scored against seeded truth.

- **1.6%** error on aggregate turnover (taxable share within 1%)
- **43 days** of warning before the threshold crossing
- **1.3 a day** median questions, 189 in a year, never over three
- **zero** credits left untagged

**The honest baseline.** A 50-line rules-only classifier gets 99.3% on sale vs not-a-sale but
catches only 77.8% of non-sale credits. That residue alone puts two eval merchants on the
wrong side of ₹40L.

She corrected the agent 52 times that year. Those corrections are the ledger's strongest
evidence, not its failures.

> Synthetic data with known ground truth. Never claim real-world accuracy.

---

## Slide 14 — Tech stack

- **n8n** — the deterministic spine. Every action the agent takes is a step you can inspect.
- **Sarvam** — Kannada speech in and out, because she is behind a counter with one phone.
- **Deterministic Python skills** — turnover, projections and apportionment are versioned and
  testable. Arithmetic never lives in the model. Wrapping arithmetic in an LLM is the standard
  tell and the trace would show it.
- **Hosted data service** — every number in a pack traces back to the credit and the
  attestation behind it.
- **Append-only chained ledger** — provenance, so the record proves when it was made.

**Permissions are the product.** The nightly pass proposes and can never commit. Only the
conversation with the merchant can record her claim. The evidence assembler is read-only and
cannot edit a classification to make a pack look better. Escalation can halt anything.

> Demo the refusal live. Ten seconds, disproportionate credibility.

---

## Slide 15 — USP

**Why this is Paytm and nobody else.**

Khatabook and Vyapar keep books after the fact. ClearTax files after the fact. Neither sits on
the rail at the moment money moves. Classification is cheap at the instant of the transaction
and unrecoverable eighteen months later.

**Why now.** The January 2026 SOP made the distinction between a mule and a shopkeeper into a
legal requirement. Nothing was built to make it operable.

**What no one else can assemble:** the bill, the device, the location, the payment history, both
sides of the transaction, and a standing channel to the banks and the police.

---

## Slide 16 — Business model

**Merchant side, defensive.** A frozen merchant transacts zero that morning. A frightened one
takes the QR down permanently. Every merchant retained is retained GMV, a live Soundbox
subscription, and a lending relationship that still exists. This is the cheapest retention spend
Paytm has, because the alternative is re-acquiring the merchant.

**Merchant side, offensive.** A merchant with a defensible turnover record is a merchant who
can be underwritten. Documented income is the single biggest blocker to small-merchant credit,
and financial services distribution is Paytm's fastest-growing revenue line. Formalisation is a
growth product, not a compliance cost.

**Subscription.** Sits naturally in a higher Soundbox tier alongside the AI device, priced in
rupees per month, not a separate purchase decision.

**Institutional.** Banks and payment companies face the same SOP duty and have none of the
data. The bona-fide-receiver determination is a service Paytm can sell to them, which is exactly
the enterprise-agent thesis Paytm is already pursuing.

---

## Slide 17 — The line we do not cross

- We never assert innocence on a freeze. We assemble evidence; a human decides.
- We file nothing with any authority ourselves without human approval.
- We compute what she genuinely owes and say so, including "you crossed the threshold, you
  must register."
- We never assert a final liability. We show the workings and route to a professional.
- We sort. We do not advocate.

**Paytm Hisaab — every rupee, on your side.**

---

## Cut from v1

- Slide 5's breakdown led by own-account and family money. Keep the arithmetic, lose the framing.
- Slide 11's box, "and yes, two of those three should not be there." Delete entirely. It argues
  the merchant's case on the exact ground where you already lost the argument.
- Slide 15's "A business QR is not for personal money. We do not excuse it." Same reason.
- All Phinite branding and the two-graph architecture diagram, unless Phinite is somehow present.

## Before the 19th

1. **You have no scale number for freezes.** You have a vivid anecdote for tax and nothing for
   the half you're now leading with. Find NCRP or I4C complaint volumes, or the petition counts
   in the Rajasthan matter. Do not invent one.
2. **Verify the SOP details from a primary or legal source**, not a news summary. You will be
   asked, and the ₹50,000 threshold and the lien-only default are load-bearing.
3. **Close the two open permission items** so the refusal demo is real.
4. **Build the evidence tiering.** You already store confidence and whether the merchant was
   asked, so most of it is surfacing data you have.
5. **Check the rules on prior work** before you commit to reusing the codebase.
