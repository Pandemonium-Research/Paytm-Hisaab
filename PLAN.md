# PLAN.md — Paytm Hisaab

**Agent Labs Buildathon · Phinite × Paytm · Track 2 (AI for Small Businesses) · Bengaluru**

> Every rupee a Paytm merchant receives is now evidence. Today it is only ever
> used *against* them. Hisaab is the agent system that lets a merchant account
> for their own money when someone in authority demands an explanation.

---

## 1. The problem

Two different authorities now read a small merchant's payment trail and draw
adverse conclusions from it. The merchant has no way to answer either.

**Tax.** Authorities compare UPI/digital collections against filed GST returns
and issue notices on the difference. Since ~2025 this has moved from catching
*unregistered* traders to auditing *registered* ones, with composition dealers
first in line because a mismatch threatens both their liability and their
scheme eligibility. Some notices assert that digital receipts are the
*minimum* turnover, on the reasoning that cash and card sit on top. Scrutiny is
extending to cash deposits, card receipts, QR collections, wallet payments and
POS data.

**Police.** Cyber-fraud money layers through several accounts fast. Any account
in the chain — including the shop at the end that sold someone a watermelon —
can be lien-marked, debit-restricted or fully frozen. The merchant is usually
not named in the FIR, often finds out only when a payment declines, and the
originating FIR is frequently in another state. A shop taking hundreds of
payments a day cannot identify which credit is disputed.

**The common failure.** Both demand the same artefact: *what was each rupee,
actually?* Gross credits are not turnover and are not proof of anything — they
include exempt supplies, cancelled orders, duplicates, refunds, and transfers
from family members sharing one account. No merchant on a QR code can produce
that breakdown. Paytm holds the data and does nothing with it.

**Consequence for Paytm.** A merchant who cannot explain their receipts takes
the QR code down. That is a dead Soundbox subscription, zero GMV, and no
lending origination — permanently.

---

## 2. The insight

Most teams would build the tax tool *or* the fraud tool. They are the same
engine with two output formats.

The shared capability is **transaction-level provenance**: a durable,
merchant-attested classification of every incoming credit. Once you have that,
computing defensible turnover and isolating a disputed payment are both
downstream reads of the same ledger.

**The wedge nobody else has.** Khatabook and Vyapar keep books after the fact.
ClearTax files returns after the fact. Neither sits on the rail at the moment
money moves. Paytm does. Classification is cheap and accurate at the instant of
the transaction and expensive and unreliable eighteen months later when the
notice arrives.

---

## 3. What we are building

### Core engine — Provenance Ledger

Every incoming credit gets a provenance tag:

| Tag | Meaning |
|---|---|
| `taxable_supply` | Ordinary sale of a taxable good/service |
| `exempt_supply` | Sale of an exempt item (vegetables, milk, unbranded goods) |
| `personal_transfer` | Money from family/self, not business income |
| `refund_reversal` | Money back from a vendor or a reversed sale |
| `duplicate` | Same sale paid twice, one later refunded |
| `inter_account` | Merchant's own money moving between their accounts |
| `non_business` | Loan, gift, deposit return — not a supply |
| `unclassified` | Insufficient signal; escalated to merchant |

**Critical design decision: the merchant attests, the agent proposes.** For a
QR-only merchant you cannot infer "personal transfer" from data alone. The
agent proposes a tag *with its reason*, and the merchant confirms or corrects
with one tap on WhatsApp. This is not a fallback — it is the point. A
merchant-attested ledger built contemporaneously is far more defensible than an
algorithmic guess produced under duress a year later, and it is the only
version that survives a hearing.

Attestation must be cheap: batched daily, only the ambiguous ones, one line
each, in the merchant's language. If the agent asks about more than ~3 credits
a day, the product is dead.

### Module A — Threshold & Mismatch Watch *(primary, build fully)*

- Projects run-rate against the ₹40 lakh (goods) / ₹20 lakh (services)
  registration thresholds off classified turnover, not gross credits.
- Tracks the gap between Paytm-collected receipts and what the merchant has
  declared, which is exactly the reconciliation authorities now perform.
- Warns *before* the gap opens, with weeks of lead time and a specific date.

### Module B — Notice Response Pack *(primary, build fully)*

On a tax notice: transaction-level classification, exemption-schedule and HSN
mapping, computed aggregate turnover with workings, and a draft reply. The
Karnataka precedent is that notices are withdrawn when a trader can *show* they
deal in exempt goods; the merchants who suffered were the ones who could not
produce records.

### Module C — Freeze Evidence Pack *(secondary, build thin)*

On a freeze: isolate the single disputed credit from the day's hundreds,
produce the matching sale record (time, amount, till, item lines if on POS),
and draft the NCRP-CFCFRMS grievance with the law-enforcement reference —
citing the line of judgments holding that only the disputed amount should be
lien-marked rather than the whole account.

Module C exists to prove the engine generalises and to give the demo its
emergency. It is one output format over the same ledger, not a second product.

---

## 4. Scope

**In:** provenance classification, merchant attestation loop, threshold
projection, mismatch detection, tax evidence pack, freeze evidence pack,
WhatsApp conversation, one regional language besides English.

**Out, deliberately:**

- Filing anything with any authority on the merchant's behalf. We produce
  artefacts; the merchant or their CA files.
- Asserting a final liability figure. See §7.
- Cash sales capture. Real, and out of scope — we handle the digital trail and
  say so plainly.
- Anything resembling marketing, loyalty, or demand forecasting. Paytm already
  ships m'Loyal and Payment Analytics; that space is occupied.

---

## 5. Architecture

Four agents. Everything deterministic is a Phinite **skill**, not an LLM call —
wrapping arithmetic in a model is the standard tell of an inexperienced team
and the trace will show it.

### Agents (genuine judgment / ambiguity / language)

| Agent | Job | Why it's an agent |
|---|---|---|
| **Provenance** | Propose a tag + reason for each credit | Ambiguous evidence; must weigh amount, timing, payer pattern, merchant history |
| **Evidence** | Assemble packs; map to exemption schedules, HSN, circulars, judgments | Selecting which authority applies to which fact |
| **Merchant** | The conversation — attestation, alerts, explanation | Regional language, low literacy, one-tap UX, tone under stress |
| **Escalation** | Decide when to stop and route to a human CA/lawyer | Knowing the limits of its own authority |

### Skills (deterministic, testable, traceable)

```
get_credit                  get_payer_history
classify_credit_rules       propose_tag
commit_attestation          get_attestation_queue
compute_aggregate_turnover  project_threshold_breach
isolate_disputed_credit     build_evidence_pack
```

Built and verified against the live service. Three more are P1: `map_hsn_exemption`,
`detect_return_mismatch`, `draft_ncrp_grievance`. Parameters and test values are in
[phinite/TOOL_SCHEMAS.md](phinite/TOOL_SCHEMAS.md); the running order is in
[BUILD_PLAN.md](BUILD_PLAN.md).

`classify_credit_rules` is the one that keeps the agent count honest: it settles the credits
that need no judgement, so the Provenance agent only reasons about the ~1% that do.

### Permission boundaries (matters for the Phinite identity story)

- Provenance Agent: read ledger, write *proposed* tags only. Cannot finalise.
- Merchant Agent: the only agent that can commit an attested tag.
- Evidence Agent: read-only over the ledger. Cannot modify a classification to
  make a pack look better.
- Escalation Agent: can halt any pack from being delivered.

### Phinite mapping

- **Identity** → agent registry entries with the scoped permissions above.
- **Skills** → the deterministic layer, versioned and shared across agents.
- **Sandbox → production** → isolated dev/UAT/prod, with *merchant attestation*
  as the promotion boundary: nothing enters a production evidence pack that a
  merchant has not confirmed.
- **Observability** → the trace is part of the pitch. Every number in an
  evidence pack should be clickable back to the credit and the attestation that
  produced it.

---

## 6. Data

No real merchant data will be available. Generate synthetically, from a known
process, so there is **ground truth** to score against:

- Per-merchant daily transaction stream with day-of-week and hour seasonality.
- Seeded ground-truth provenance labels across all eight tags.
- A deliberate mix: exempt-goods merchant, mixed taxable merchant, and a
  merchant whose personal and business credits share one account.
- One merchant seeded to cross ₹40 lakh mid-year.
- One credit seeded as fraud-linked, three layers downstream of a victim.

This lets you demo the classifier *recovering* the true labels and report a
real accuracy number rather than vibes. Roughly 90 minutes of work and no other
team will have it.

**Built.** `python -m synth.generate` produces demo, dev, eval and difficulty-sweep splits,
each separated into `visible/` (what agents may read) and `hidden/` (the answers). How it was
generated, what it means for the build, the evaluation targets and the caveats are in
[DATA.md](DATA.md); the column reference is [data/README.md](data/README.md).

---

## 7. The framing that cannot be got wrong

**Accuracy, not minimisation.**

Pitch this wrong and it reads as a tax-avoidance tool sold to a listed payments
company, and it dies in the first question.

Non-negotiables:

1. The agent computes what the merchant genuinely owes and says so plainly.
   **A mandatory demo beat:** it tells a merchant *"you crossed the threshold on
   14 March. You need to register. Here is the estimated cost."*
2. It never asserts a final liability figure on its own authority. It computes,
   shows workings, and routes to a CA.
3. On freezes: some frozen accounts genuinely are mule accounts. The agent
   assembles evidence; it does not assert innocence.
4. Nothing is filed by us. Artefacts only.
5. No advice framing anywhere. This is books and evidence.

---

## 8. Verify before building — kill conditions

Resolve these first. Any one of them can reshape or end the project.

| # | Question | If the answer is bad |
|---|---|---|
| 1 | Does the sandbox expose merchant transaction records with a **stable payer identifier** across repeat transactions? | Fatal for attestation UX; fall back to amount+time only |
| 2 | Item-line / HSN data for POS merchants — available, or QR-only? | Determines whether exemption mapping is real or simulated |
| 3 | Can we write back to a merchant-scoped store, or is everything read-only? | Ledger has to live somewhere |
| 4 | Is there any usable WhatsApp path (Connect Plus or otherwise) in the sandbox? | Merchant Agent falls back to in-app/API; weakens the demo, not fatal |
| 5 | Does Paytm treat tax as a third rail? | Reweight the pitch toward Module C and lending-readiness |
| 6 | Freeze standing: Paytm has the evidence but no standing in the police process | Framing fix — Paytm supplies, merchant files. Confirm this is acceptable |

---

## 9. Risks

- **Scope.** Two modules plus an engine is already at the edge. If time
  compresses, cut Module C to a static rendered pack. Do not cut attestation.
- **Classifier credibility.** With thin signal, refuse to guess. An
  `unclassified` tag routed to the merchant is a *feature*; a confident wrong
  tag in an evidence pack is a catastrophe.
- **Agent theatre.** Four agents is the ceiling. If a reviewer can replace an
  agent with twenty lines of Python, it should have been a skill.
- **Legal exposure.** Escalation Agent is not optional garnish; it is what makes
  the product shippable.
- **Demo fragility.** Rehearse until nothing depends on a live external call.

---

## 10. Metrics to claim on stage

Measured on the demo merchant (a year, 13,267 credits). Re-run with
`python -m tools.simulate_year --reset` and `python -m tools.check_beats`.

- **Turnover accuracy:** aggregate turnover within **1.6%** of the seeded truth, against a
  notice claiming ₹60.98L of receipts as income. The taxable share — the part tax is actually
  paid on — lands within **1%** (₹10.87L against ₹10.73L), because unbilled QR sales are
  apportioned by value from the shop's billed ratio rather than labelled wholesale one way.
- **Attestation burden:** **189 questions across the year, median 1.3 a day**, none over the
  ≤3/day budget. The merchant corrected 52 of them.
- **Lead time:** projecting from 31 Jan lands within a day of the true crossing date, **43 days
  of warning**.
- **Isolation:** the disputed ₹4,200 found by UTR *and* by amount and date, with the innocent
  same-amount payment that week listed but not chosen.
- **Classifier floor:** a rules-only baseline on the held-out eval split gets 99.3% on sale vs
  not-a-sale and **77.8% recall on non-sale credits** ([DATA.md](DATA.md) §6.3). Report what the
  agent adds over that, and the `unclassified` rate, honestly.

---

## 11. Demo — four beats

Demoed on Web Chat in Kannada; WhatsApp is the production path and needs credentials we
decided not to wait for. Every figure below comes out of the running system — the answer key
is `data/demo/hidden/demo_scenario.json`.

1. **Ordinary Tuesday.** Tuesday 10 March, three credits from the weekend, one tap each:
   ₹15,000 at 11:04pm Sunday from her own savings account (*her own money, not a sale*);
   ₹7,500 from her husband on Monday afternoon, scanned at the shop QR like any customer;
   ₹4,850 from Raghu Shetty, who has bought twice before — a real sale, and the agent asks
   rather than assuming. Nothing else is surfaced: the other 36 credits those days are
   ordinary sales, and a ₹23 payment nobody can place is left alone.
2. **The warning.** Replaying as of 31 January: "at your current rate you cross ₹40 lakh
   around 14 March. You will need to register." Six weeks of warning, and the date is
   computed, not typed. *(This beat is what makes the pitch safe.)*
3. **The notice.** A notice claims **₹60.98 lakh** of turnover. The pack: **₹42.2 lakh**
   aggregate turnover — ₹31.3L exempt, ₹10.9L taxable — and ₹18.8 lakh that is not turnover
   at all: ₹7.4L moved between her own accounts, ₹6.1L family money, ₹4.3L loan and chit
   payouts, ₹0.5L supplier refunds, ₹0.5L duplicates. Every line traces to transaction IDs.
   And it says plainly that she *did* cross ₹40 lakh and must register.
4. **The emergency.** Account frozen Tuesday morning, supplier payment due. The agent isolates
   the disputed ₹4,200 credit from the 339 payments that week, produces the sale record (12kg
   onions and the rest, POS bill, till, 19:47), and drafts the grievance citing the
   lien-only-the-disputed-amount judgments. A second ₹4,200 payment that week, from a regular
   customer, is listed and *not* chosen.

Beat 3 is the product. Beat 4 is the moment people remember. Beat 2 is what
stops the room turning hostile.

---

## 12. Naming

"Hisaab" works — account, reckoning, *"hisaab do"*. Low priority; do not spend
time here. Check it does not collide with an existing Paytm surface.

---

## Appendix — Sources

**GST scrutiny on digital payment data (current, national)**
- https://www.jurishour.in/columns/gst-notice-upi-payments-small-businesses-india/ — May 2026; registered traders and composition dealers now in scope
- https://www.caclubindia.com/articles/gst-notices-on-the-rise-key-issues-common-mismatches-and-major-compliance-areas-taxpayers-must-review-56163.asp — Aug 2026 notice volume and mismatch categories
- https://cleartax.in/s/gst-news-and-announcements — AATO auto-update, 2026 amendment window
- https://taxguru.in/goods-and-service-tax/upi-data-gst-notices-legal-defenses-traders.html — turnover ≠ credits; statutory defences

**Karnataka episode (2025, context — do not present as current)**
- https://www.deccanherald.com/amp/story/india%2Fkarnataka%2Fvegetable-vendor-from-haveri-getsrs-29l-tax-demand-3639536
- https://www.deccanherald.com/amp/story/india%2Fkarnataka%2Fbengaluru%2Fupi-dilemma-bengalurus-small-vendors-fear-big-trouble-over-tax-notice-3632149
- https://www.thenewsminute.com/karnataka/karnataka-how-a-vegetable-vendors-gst-notice-triggered-a-statewide-upi-boycott
- https://blog.saginfotech.com/karnatakas-gst-evasion-notices-prompt-shopkeepers-upi-payments
- https://www.etvbharat.com/en/!bharat/from-digital-to-cash-karnataka-small-traders-avoid-upi-payments-amid-gst-crackdown-enn25072002295
- https://thelogicalindian.com/karnataka-withdraws-upi-tax-notices-following-vendor-protests-across-the-state/

**Account freezes (current)**
- https://www.medianama.com/2026/07/223-merchants-bank-accounts-frozen-upi-payments-fraudsters-andhra-hc/ — AP High Court, July 2026
- https://mas360.moneylife.in/cyber-awareness/fraud-alert-beware-police-are-freezing-bank-accounts-for-accepting-payment-from-upi-accounts-linked-with-cybercrimes/4485.html
- https://www.aparlaw.com/post/bank-account-frozen-due-to-a-cyber-crime-complaint-what-to-do-in-india — NCRP-CFCFRMS remedy path
- https://netlawgic.com/bank-account-freeze-in-cyber-crime-cases-share-trading-fraud-crypto-fraud-money-mule-accounts-and-liability-of-account-holders-in-india/ — lien vs debit freeze vs full freeze
- https://www.legals365.com/legal-blogs/bank-account-frozen-in-cyber-crime-case/ — cross-state FIRs
- https://saroshdamania.com/bank-account-frozen-cyber-crime-defreeze/ — Sept 2026

**Paytm surfaces**
- https://business.paytm.com/pos-billing-software
- https://business.paytm.com/connect-plus
- https://business.paytm.com/paytmmloyal
