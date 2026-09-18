# DATA.md — Hisaab synthetic data

This document covers how the data was made, what it means for the build, and how to tell whether
the agent is doing well. It is the companion to [PLAN.md](PLAN.md) §6. File formats and columns
are in [data/README.md](data/README.md).

---

## 0. The short version

- **Why generate it.** There is no real merchant data, so we generated it from a known process.
  Every incoming payment has a hidden true answer: sale, family money, refund, and so on. That
  lets us report a real accuracy number instead of vibes.
- **The one rule.** Anything the product builds reads `data/<split>/visible/` only. `hidden/`
  holds the answers and is for scoring and demo checks. If agent code ever reads `hidden/`, every
  number we show is fake.
- **The hard part is small.** About 98.6% of payments are ordinary sales. The hard part is the
  other ~1.4%: family money, the merchant's own top-ups, loans, refunds and duplicates. Those
  inflate "turnover" if they are missed.
- **A 50-line rule baseline** gets sale vs not-a-sale right 99.3% of the time but catches only
  **77.8%** of the non-sale payments. Its turnover errors are small in percentage terms (+4–8%),
  yet big enough to put two eval merchants on the **wrong side of the ₹40L line**. That is the
  gap the agent plus merchant confirmation has to close.
- **The demo world is ready.** Sahana Stores, a Jayanagar shop, is seeded with all four PLAN §11
  beats. The true answers are in `data/demo/hidden/demo_scenario.json`.
- **Two corrections to PLAN.md.** GST turnover *includes* exempt sales, and the beat-3 numbers
  in PLAN §11 are internally inconsistent (see §4).

---

## 1. Why synthetic, and why the visible/hidden split matters

The pitch claims the agent can recover *what each rupee actually was*. You can only measure that
if you know the truth. So we wrote a simulator that plays out a year of a shop's life. It decides
the truth first (this payment is the spouse sending household money), then produces only what
Paytm would actually see: amount, time, payer VPA, payer name, channel and UPI note.

```
merchant profile  ->  daily sales  ->  duplicates / refunds  ->  suppliers & own-account top-ups
                  ->  family transfers  ->  loans / chit / gifts  ->  fraud chain
                                         |
                    +--------------------+--------------------+
                    v                                         v
         visible/  (what Paytm sees)               hidden/  (what really happened)
                    |                                         |
               Hisaab agents  ->  proposed labels  ->  synth.score  <--+
```

The generator knows nothing about the classifier. If you "fix" accuracy by reading `hidden/`,
or by writing rules that copy the generator's code, the number stops meaning anything. The eval
split exists to catch the second failure (§6).

---

## 2. How the data was created

All the code is in `synth/`. It uses only the Python standard library and fixed seeds, so every
run reproduces the same files. Knobs per shop type live in `synth/catalog.py`; the process lives
in `synth/world.py`.

### 2.1 Merchant setup
Each merchant gets the following:

- **An owner and two own accounts.** One is a savings VPA, always linked in the Paytm profile.
  The other is a personal UPI ID, linked only at low difficulty.
- **Four family members:** spouse, sibling, parent, in-law. They usually share the owner's
  surname.
- **A pool of regular customers plus walk-ins.** Regulars follow a "few customers buy a lot"
  curve; walk-ins are new payers every time.
- **2–4 suppliers.**

Every counterparty has a stable `counterparty_id`. This assumes PLAN §8 kill-condition #1 (a
stable payer ID) comes back "yes".

### 2.2 Sales (the bulk of the data)
- **Daily volume** = base rate × day of week (weekends +20–25%) × month × festival bump
  (Deepavali, Ganesha, Ugadi, Sankranti and others) × compounding monthly growth × random noise.
  The actual count is a random draw around that. The shop is shut on about 1% of days.
- **Time of day** follows a shop-specific curve: morning and evening peaks for a kirana, meal
  peaks for a darshini.
- **Each sale is a basket** of 1–6 items drawn from `ITEMS` in `catalog.py`. There are 41 items
  with HSN codes. Exempt items include fresh vegetables, loose milk and loose rice; taxable items
  include branded rice, oil, soap and biscuits. Line values are random within item-specific
  ranges, and occasional bulk orders multiply them 4–15×.
  - The payment **amount is the basket total**.
  - The **true label is whichever side (exempt or taxable) holds the majority of the value**.
  - The exact rupee split is stored in `exempt_value` / `taxable_value`.
- **Channel.** A share of sales go through POS, which produces an **itemised bill** (visible).
  The rest are Soundbox QR scans, which carry no item list.
- **Hard negatives.** A few customers genuinely buy the same thing twice within ~20 minutes.
  These look exactly like duplicates but are real sales.

### 2.3 Non-sale payments, each with a realistic "signature"
| Label | How it's generated | Clues it leaves (fewer at higher difficulty) |
|---|---|---|
| `duplicate` | ~0.8% of QR sales get an identical second payment seconds to minutes later. Usually one is refunded, with the refund linked to it. Sometimes the merchant refunds the *first* one, which then becomes the duplicate. | same payer + amount, short gap, a refund row with `orig_txn_id` |
| `refund_reversal` | ~3.5% of supplier payments get 5–30% sent back (short supply, crate return). ~0.7% of payouts fail and bounce back. | the payer is someone the merchant paid; `UPI_REVERSAL` channel |
| `inter_account` | Top-ups from the owner's own accounts minutes before a big supplier payment, plus about one month-start top-up a month. | owner's name, linked VPA, round ₹1k/₹5k, just before a supplier payment |
| `personal_transfer` | Spouse ~2×/month, sibling, parent, in-law. | round amounts, late night / early morning, paid straight to the VPA rather than scanned, shared surname, notes like "mane kharchu" |
| `non_business` | Loan disbursal (₹1–3L by bank transfer), chit-fund payouts (non-round: chit value minus auction discount), festival gifts from friends (₹501 / ₹1,001 / ₹2,001), hand loans repaid, a rent deposit returned, an insurance claim. | bank transfer, lender or chit company name, "01"-ending amounts, notes |

Suppliers are paid every few days from the shop's recent sales. The owner also sweeps money to
savings on some Sunday nights. These **debits are visible**; they are context for the credits,
not things to classify.

### 2.4 The difficulty knob (d = 0 → 1, set per merchant)
One number controls how often the clues above appear:

- round amounts
- off-hours timing
- direct-to-VPA channel vs QR
- shared surname (names get abbreviated to "K GOWDA" / "SAHANA G")
- UPI notes
- whether the second own account is linked (only when d < 0.5)
- the gap between duplicate payments (up to 2 min at d=0 → up to 30 min at d=1)
- whether the duplicate was refunded at all (95% → 60%)
- whether the refund hits the "wrong" twin

At d=1 a spouse transfer can be ₹4,850 at 2pm via QR with no note and an abbreviated name,
which is indistinguishable from a sale. The `cues` column in `hidden/ground_truth.csv` records
which clues each payment actually carries, so you can see *why* the agent missed something.

### 2.5 The fraud chain (Module C)
A victim in another state is scammed of ₹50,000, which goes to mule A. Mule A splits it:
₹20,000 to mule B and more to two other mules. A day later mule B **buys goods** at the merchant
(₹4,200 in the demo). The merchant's payment is a **genuine sale**; it is labelled as a sale.
Being fraud-linked is recorded separately, because provenance and fraud linkage are different
questions.

2–5 days later a freeze event arrives. It carries the police unit, NCRP acknowledgement, amount,
date and UTR. The full chain is hidden in `fraud_chains.json`.

### 2.6 Tax-side events
- **Tax notice.** The notice's `claimed_turnover` is simply *all incoming money for the year*,
  mirroring how authorities read UPI data.
- **Composition merchant.** It files quarterly CMP-08 returns. Half the quarters are
  under-declared (70–92% of true turnover), so there is a mismatch to detect.

### 2.7 Demo calibration
For Sahana Stores all ordinary sales are scaled by one factor so that **aggregate turnover
crosses ₹40L on 14 Mar 2026**. The code asserts this on every run. The seeded demo payments are
pinned and not scaled. Other non-sale payments on 8–9 Mar are removed, so beat 1 shows exactly
three.

---

## 3. What's in it

| Split | Contents | Window | Purpose |
|---|---|---|---|
| `demo` | Sahana Stores, 13,267 credits | FY 2025-26 | the four demo beats |
| `dev` | 7 merchants, ~107k credits | FY 2025-26 | build and tune freely |
| `eval` | the same 7 shop types, new seed and difficulties, ~107k credits | FY 2025-26 | report numbers; **don't tune on it** |
| `sweep` | family_kirana at d = 0, 0.25, 0.5, 0.75, 1 | Oct 2025 – Mar 2026 | accuracy-vs-difficulty curve |

**The eval merchants.** Totals are for FY 2025-26; "aggregate" means taxable + exempt sales only.

| ID | Type | d | All money in | Aggregate turnover | Truth |
|---|---|---|---|---|---|
| EV_001 | veg_vendor | 0.5 | ₹51.7L | ₹40.6L | over ₹40L but **exclusively exempt → no registration needed** |
| EV_002 | mixed_kirana | 0.7 | ₹63.4L | ₹52.1L | crossed 9 Jan 2026; gets a tax notice |
| EV_003 | family_kirana | 0.3 | ₹65.4L | ₹39.0L | **under** ₹40L despite ₹65L coming in |
| EV_004 | family_kirana | 0.9 | ₹63.0L | ₹39.9L | **under by ₹10k**; has the fraud chain |
| EV_005 | mobile_accessories | 0.2 | ₹78.7L | ₹60.3L | crossed 13 Dec 2025 |
| EV_006 | darshini (services) | 0.6 | ₹58.6L | ₹47.6L | crossed the **₹20L services** line on 10 Sep 2025 |
| EV_007 | composition_kirana | 0.6 | ₹77.7L | ₹59.7L | already registered; CMP-08 mismatches to detect |

The label mix in eval: 98.6% sales, 0.6% duplicates, 0.5% own-account, 0.3% personal, 0.1%
refunds, 0.04% non-business (only 38 payments, so per-class numbers for it are noisy).

---

## 4. Design decisions, and corrections to PLAN.md / the ChatGPT note

1. **Aggregate turnover includes exempt sales** (CGST Act s.2(6)). The ChatGPT note computed
   the ₹40L crossing on *taxable* turnover only, which is wrong. Only a supplier dealing
   *exclusively* in exempt goods is spared registration (s.23); that is the Haveri vegetable
   vendor story, and our `veg_vendor`. Thresholds used are ₹40L for goods and ₹20L for services.
2. **PLAN §11 beat 3 numbers need replacing.** "₹41L exempt + ₹13L taxable" is ₹54L of
   turnover, which is already well over ₹40L. Use the demo truth instead: the notice claims
   **₹61.0L**; the truth is **₹42.9L aggregate** (₹32.1L exempt + ₹10.7L taxable), ₹7.4L own
   accounts, ₹5.7L personal, ₹4.3L loans/chit/gifts and ₹0.7L refunds and duplicates. So the
   honest pack says: *"the ₹61L claim is wrong, and you did cross ₹40L, on 14 March."* That
   also delivers PLAN §7's mandatory "you need to register" beat.
3. **PLAN §11 beat 1 wording.** "₹15,000 from a VPA matching your savings account — personal
   transfer?" By our labels that is `inter_account` (her own money), not family money. Suggested
   wording: *"your own money from your savings account?"*
4. **`unclassified` is never a true answer.** It is something the agent is allowed to say.
   There are seven true labels, which lets us measure the refuse-to-guess rate (PLAN §9).
5. **Label conventions where PLAN's tags overlap.** The agent's prompt must use the same
   definitions, or it will be marked "wrong" on a convention:
   - `personal_transfer` = from household family (spouse, sibling, parent, in-law).
   - `inter_account` = from an account in the owner's own name.
   - Gifts from *friends / extended family*, hand loans repaid, deposits, chit, loans and
     insurance = `non_business`.
   - `duplicate` = the refunded twin, or the later twin if neither was refunded.
   - A sale's exempt/taxable label = the majority of basket value.
6. **Realistic frequencies.** The ChatGPT note suggested 5% personal transfers. By *count*,
   real shops see far fewer. By *value* they matter a lot: 9% of Sahana's receipts are personal.
   We kept realistic counts, which is why rupee-level metrics matter more than raw accuracy (§6).
7. **No "training set" of 50 merchants.** Nothing is being trained. Dev, eval, sweep and demo
   are enough.

---

## 5. What this means for the build (component by component)

### Everything
- **Read `visible/` only.** Build a ledger store keyed by `txn_id` (PLAN §8 kill-condition #3)
  that holds *proposed* and *attested* tags. Never copy `hidden/` into it.
- **Most of the signal is relational, not in the single row.** It comes from questions like:
  - Has this payer paid before, how much, and how?
  - Did the merchant ever *pay* them?
  - Is there a twin payment?
  - Was it refunded (`orig_txn_id`)?
  - Does the payer match a linked own account or the owner's surname?

  Build these as deterministic **skills** (a payer-history lookup, a twin finder, a refund
  linker) and hand the agent their output, not raw CSV.
- **Don't call an LLM on every payment.** 98.6% are routine sales; rules settle them. Send only
  the leftover ~1–2% to the Provenance Agent. That keeps cost sane and avoids PLAN §9's "agent
  theatre" critique.
- **Don't hard-code demo txn IDs.** Read them from `demo_scenario.json`; they change if the
  generator changes.

### Provenance Agent
- **Input:** one credit plus the skill outputs above.
- **Output:** a label, a one-line reason and a confidence.
- **When unsure, say `unclassified`** and route to the Merchant Agent. A confident wrong tag in
  an evidence pack is the catastrophe PLAN §9 warns about.
- **The hard cases to get right:**
  - own second account vs spouse, e.g. "SAHANA G" on an unlinked VPA
  - family paying by QR like a customer
  - genuine same-amount repeat purchases vs duplicates
  - hand loans repaid vs family money

### Exempt vs taxable
- **POS-billed sales:** map items via `data/reference/hsn_catalog.json`; this is exact.
- **QR-only sales at a mixed shop:** there is no item list, so **don't try per payment.**
  Estimate the exempt share in aggregate, either from that shop's POS bills or by asking the
  merchant once, and label it as an estimate in the pack.
- **HSN code alone isn't enough.** HSN 1006 covers both loose rice (exempt) and branded rice
  (taxable); the `basis` field says which condition applies.
- **GST rates are not in the data.** They changed on 22 Sep 2025. If beat 2 quotes "what
  registration costs", source rates separately and have a CA check them.

### Merchant Agent (attestation)
- **Budget:** PLAN says at most ~3 questions a day. Sahana has 236 non-sale payments a year
  (~0.65 a day), so the budget holds easily as long as the agent asks only about the *ambiguous*
  ones, not about routine sales.
- **To measure "after attestation" accuracy, simulate the merchant.** For every payment the
  agent asks about, take the answer from `hidden/ground_truth.csv`, as if the merchant answered
  truthfully, within the daily budget. Then score the resulting ledger. This is the scoring
  harness's job; the agent itself never sees the answer.

### Skills (Module A and B)
- `compute_aggregate_turnover`: taxable + exempt sales only. Check against
  `merchant_truth.json → aggregate_turnover`.
- `project_threshold_breach`:
  - check crossing dates against `threshold_crossing_date`
  - use ₹20L for services (darshini)
  - return "registration not required" for exclusively-exempt shops, even above ₹40L
  - for the beat-2 projection, replay with data up to 31 Jan 2026
- `detect_return_mismatch`: for EV_007 / DV_007, compare CMP-08 `declared_turnover` with
  Paytm receipts. The naive gap (all money in minus declared) is *overstated*; the real gap is
  true turnover minus declared (`merchant_truth.json → declared_returns`).
- `build_evidence_pack`: every number must trace back to `txn_id`s and their attestation (PLAN
  §5 observability).

### Module C
- **`isolate_disputed_credit`:** match the freeze event's `disputed_utr` to a txn. Also handle
  the amount-only fallback: Sahana has **two ₹4,200 payments that week**, and only the date
  separates them.
- **The pack:** the matching sale's POS bill (items, time, till `POS01`), the payer details and
  the NCRP grievance.
- **Tone:** the agent must not assert the merchant is innocent (PLAN §7.3). The data backs this:
  the sale is real, but the payer really was a mule.

### If the Paytm sandbox differs from our assumptions (PLAN §8)
| Finding | What to do with this data |
|---|---|
| No stable payer ID | Blank the `counterparty_id` column and re-run. Payer-history skills fall back to handle and name, and accuracy will drop; that's the honest number. |
| QR only, no item lines | Ignore `pos_bill_lines.csv`. Exempt vs taxable becomes aggregate-estimate only. |
| No write-back store | Keep the ledger in local SQLite or JSON for the demo. |

---

## 6. How to evaluate the agent

### 6.1 Commands
```
python -m synth.baseline data/eval                                   # rule baseline
python -m synth.score data/eval data/eval/predictions_baseline.csv   # score it
python -m synth.score data/eval my_predictions.csv                   # score your agent
```
A predictions file needs only `txn_id,label`. You can score a sample; you don't need to run all
~107k credits. For the Provenance Agent, score the credits your rules forwarded to it.

### 6.2 What the metrics mean
| Metric | Meaning | Why it matters |
|---|---|---|
| Provenance accuracy (sale vs not-a-sale, with the exact type for non-sales) | Taxable and exempt are folded into "sale" | This is what decides turnover |
| **Recall on non-sale credits** | Of the payments that aren't sales, the share labelled correctly | The core skill; misses inflate turnover |
| False-confidence rate | Committed to a label and got it wrong | PLAN §9: worse than saying unclassified |
| Unclassified rate | Share of payments the agent refused to guess | Must fit the attestation budget |
| Exempt vs taxable (POS / QR) | Reported separately | Per-payment QR is not identifiable |
| **Turnover error, in ₹** | Predicted vs true turnover per merchant (the `pred supply` vs `true supply` columns) | This is what the evidence pack actually asserts |
| Exact 7-way accuracy | Printed last | **Don't headline it**; the QR exempt/taxable guess dominates it |

### 6.3 Baseline results (rules only, no LLM, no merchant; eval split)
- Sale vs not-a-sale: **99.3%**. False-confidence: 0.4%. Unclassified: 0.3%.
- **Recall on non-sale credits: 77.8%** (1,511 payments).
- Per class:
  - refunds 100%
  - duplicates 93% recall
  - own-account 74%
  - non-business 61%
  - personal **51%**

  Personal transfers made by QR look like sales, and unlinked own accounts look like family.
- Exempt vs taxable: 100% on POS-billed sales; 78% on QR-only sales (47% on the sweep).
- **Turnover error:** the baseline overstates the family_kirana shops by **+4.4% (EV_003)** and
  **+8.1% (EV_004)**. That pushes both *over* ₹40L when they are really under, so the
  registration answer flips. This is the headline for why provenance matters.
- **Difficulty sweep**, non-sale recall at d = 0 / 0.25 / 0.5 / 0.75 / 1: **96% / 92% / 68% /
  61% / 57%**.

The baseline was written by someone who knows the generator, so treat it as an *optimistic*
floor.

### 6.4 Suggested targets (goals, not results; fill in the real numbers tomorrow)
| Metric (eval) | Baseline | Agent alone | After simulated attestation |
|---|---|---|---|
| Sale vs not-a-sale | 99.3% | ≥ 99.3% | ≥ 99.9% |
| Recall on non-sale credits | 77.8% | ≥ 85% | ≥ 98% |
| False-confidence on non-sale credits | high (most misses are confident) | clearly below baseline; prefer `unclassified` | ~0 |
| Turnover error per merchant | up to +8.1% | ≤ 2% | ≤ 0.5% |
| Registration answer (EV_003, EV_004 correct) | wrong on both | right on both | right on both |
| Questions to merchant | — | median ≤ 1/day, never > 3/day | same |
| Freeze: correct txn isolated, decoy rejected | — | yes | yes |
| Threshold projection from 31 Jan (demo) | — | within ~2 weeks of 14 Mar | exact on full data |

On stage, say: *"Rules alone catch 78% of non-sale money; our agent plus one-tap merchant
confirmation catches X%, and the turnover figure is within Y% — tested on a synthetic ledger with
known ground truth, including deliberately ambiguous shops."*

---

## 7. Demo answer key (Sahana Stores, `MID_DEMO_SAHANA`)

Check live output against `data/demo/hidden/demo_scenario.json`. Current values:

**Beat 1 — Tue 10 Mar 2026.** Surface exactly three payments from 8–9 Mar:

| # | Payment | Truth | Why it's hard |
|---|---|---|---|
| 1 | ₹15,000, Sun 23:04, from `sahanagow29@oksbi` (her linked savings), `DM0012559` | `inter_account` | easy; confirm |
| 2 | ₹7,500, Mon 13:20, from MANJUNATH GOWDA (spouse) **via QR**, `DM0012580` | `personal_transfer` | business hours, scanned like a customer; surname and history are the clues |
| 3 | ₹4,850, Mon 16:40, from RAGHU SHETTY, `DM0012583` | a sale (`exempt_supply`) | big for this shop, but he bought ₹2,300 (24 Jan) and ₹3,100 (17 Feb) before; the agent should ask, not assume a transfer |

**Beat 2.** Aggregate turnover crosses ₹40,00,000 on **14 Mar 2026**. When projecting from
31 Jan 2026 the agent should land near that date, then say *"you need to register"* and route to
a CA (PLAN §7). Under CGST s.25, the application is due within 30 days of becoming liable;
confirm with the CA.

**Beat 3 — notice dated 20 Aug 2026** (`SYN/CTD/2026-27/00417`), claiming **₹60,98,462**:

| Line | Amount |
|---|---|
| Exempt sales | ₹32.14L |
| Taxable sales | ₹10.75L |
| Own-account transfers | ₹7.36L |
| Personal / family | ₹5.73L |
| Loans, chit, gifts, other non-business | ₹4.26L |
| Refunds from suppliers / reversals | ₹0.47L |
| Duplicates | ₹0.27L |
| **Aggregate turnover** | **₹42.89L**, over ₹40L, so registration was required |

**Beat 4 — freeze at 09:30 on Tue 24 Mar 2026**, Cyber Crime PS Hyderabad (NCRP ack
`SYN-31703260045812`):

- **Disputed payment:** ₹4,200 at 19:47 on 21 Mar, UTR `608019013171` → `DM0013171`. It is a
  POS-billed genuine sale.
- **Decoy:** ₹4,200 on 18 Mar from a regular customer, `DM0012998`.
- **The haystack:** 339 payments in the 7 days before the freeze.

---

## 8. Caveats: what not to claim

- **This is synthetic.** Distributions are plausible, not calibrated to real Paytm data. Claim
  "on a synthetic ledger with known ground truth at difficulty d", never real-world accuracy.
- **Don't tune on eval.** Build on dev, report eval once. Rules that mirror `synth/world.py`
  will look great and prove nothing.
- **Label conventions are ours** (§4.5). Put the definitions in the agent's prompt.
- **Small classes are noisy.** There are only 38 non-business payments in eval; quote them with
  counts, not bare percentages.
- **The dates are FY 2025-26** (Apr 2025 – Mar 2026), shown as a replay. The notice (Aug 2026)
  is about that year, which is consistent. Present beats 1, 2 and 4 as "here's what Hisaab would
  have done".
- **Legal points are summarised for engineering, not advice.** Before stage, have a CA sanity
  check the aggregate-turnover definition, exclusive-exempt exemption, ₹40L/₹20L thresholds and
  the 30-day registration window.
- **Everything is fictional:** names, VPAs, businesses, lenders, chit funds, police references
  (`SYN-` prefixed). Phone-style VPAs are masked (`98XXXXXX21@ybl`).

---

## 9. Regenerating or changing the data

```
python -m synth.generate                 # all splits (~1 min)
python -m synth.generate --only demo
```

- **Shop behaviour:** change it in `synth/catalog.py → ARCHETYPES` (volumes, POS share, family
  intensity and so on).
- **Which merchants are in each split:** edit `synth/generate.py → SPLITS`.
- **Seeds:** set in `SEEDS`. Same code plus same seed gives identical files.
- **The demo's 14 Mar crossing is enforced by an assert.** If you change the demo archetype and
  it fails, the calibration couldn't hit that date; adjust `avg_daily` / `growth`.
- **After any change,** re-run the baseline and scorer, and update §3, §6.3 and §7 of this file.
