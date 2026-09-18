# Synthetic world v2 (`sim/`)

No real merchant data is available, so this generator plays out a year in each shop's life from a
known process. It decides what really happened first, then writes only what Paytm would see.
Every credit therefore has a hidden true answer, and every accuracy number is measured, not
guessed.

This is Phase 3 of [PHASES.md](../PHASES.md) and §5 of
[IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md). It is a clean rewrite. The v1 design notes
in [DATA.md](../archive/agent-labs-2026-09-12/DATA.md) were its specification, but no v1 code or
results are reused.

> **The one rule.** Product code (core, n8n workflows, the memory service, the web app) reads
> `data/<split>/visible/` only. `hidden/` is for `eval/`, the demo answer key and the
> simulated-merchant harness. If product code ever opens `hidden/`, every number we show is fake.

## Commands

```bash
python -m sim.generate                    # all splits, about 30 s, validates each one
python -m sim.generate --only demo        # just the demo split
python -m sim.validate data/demo          # re-check a split on disk
python -m eval.baseline data/eval         # rules-only floor -> data/eval/predictions_baseline.csv
python -m eval.score data/eval data/eval/predictions_baseline.csv [--json report.json]
```

The generator needs only the standard library. Pillow is optional: with it, each notice also gets a
phone-photo JPG. Fixed seeds mean the same code always gives byte-identical files. `data/` is
gitignored, so regenerate after pulling. The old v1 splits were moved to `data/_v1/`.

## Splits

| Split | Merchants | Window | Use |
|---|---|---|---|
| `demo` | Sahana Stores (Bengaluru, Kannada) and Maurya Sabzi Bhandar (Lucknow, Hindi), about 39k credits | FY 2025-26 | the demo beats |
| `dev` | 7 shop types, mixed difficulty, about 111k credits | FY 2025-26 | build and tune freely |
| `eval` | the same 7 shop types, new seed and difficulties, about 110k credits | FY 2025-26 | report numbers; **don't tune on it** |
| `sweep` | `family_kirana` at d = 0, 0.25, 0.5, 0.75, 1 | Oct 2025 – Mar 2026 | accuracy-vs-difficulty curve |

**Dev and eval shop types**
- **`veg_vendor`:** calibrated just above ₹40L, but every sale is exempt, so it need not register.
- **`mixed_kirana`:** gets a tax notice.
- **`family_kirana` ×2:** calibrated just *under* ₹40L while ₹47–50L comes in. Miscounting
  family money flips the registration answer. One of the pair has the fraud chain and freeze.
- **`mobile_accessories`:** all taxable; gets a police inquiry.
- **`darshini`:** restaurant services, so the ₹20L threshold applies.
- **`composition_kirana`:** already registered, with under-declared CMP-08 quarters.

Merchants span Kannada, Hindi, Tamil, Telugu, Marathi and Bengali.

## Layout

```
data/<split>/
  manifest.json                 generator version, seed, counts, file lists (no truth)
  visible/                      what Paytm sees: the ONLY input for product code
    transactions.csv            every credit (CR) and debit (DR)
    pos_bill_lines.csv          item lines for POS-billed sales
    merchants.json              profile: category, GST status, place, language, linked own accounts
    terminals.json              Soundbox / POS device id, install date, geo
    daily_balances.csv          opening, credits, debits, closing per day
    rails_events.json           lien_marked, payment_declined, lea_inquiry, notice_served, return_filed
    hsn_catalog.json            item -> HSN -> exempt? (+ legal basis)
    notices/*.pdf, *.jpg        the paper notice, and a phone photo of it (SYNTHETIC SPECIMEN)
  hidden/                       what really happened
    ground_truth.csv            per credit: true label, reason, exempt/taxable split, cues, fraud link
    relationships.csv           duplicate_of, refund_of, repeat_of, vendor_refund_for, reversal_of
    merchant_truth.json         totals by label, aggregate turnover, crossing date, registration answer
    fraud_chains.json           victim -> mule -> mule -> this merchant, with the police reference
    merchant_answers.csv        what the merchant would answer if asked about each credit
    behaviour.json              the simulated merchant's answer model (rates, delays, corrections)
    notices_truth.json          the fields printed on each notice (for checking OCR)
    demo_scenario.json          (demo only) the answer key for every beat
```

### `visible/transactions.csv`

| Column | Meaning |
|---|---|
| `txn_id` | `DM…` / `DV…` / `EV…` / `SW…` plus 7 digits, chronological across the split |
| `merchant_id` | the merchant this row belongs to |
| `ts` | IST, ISO-8601 |
| `direction` | `CR` credit, `DR` debit |
| `amount` | whole rupees |
| `channel` | credits: `UPI_QR` (Soundbox), `UPI_POS` / `CARD_POS` (POS, has a bill), `UPI_INTENT` (paid straight to the VPA), `IMPS`, `BANK_TRANSFER`, `UPI_REVERSAL`; debits: `UPI_OUT` (supplier or own savings), `REFUND` (to a customer) |
| `counterparty_id` | stable payer id |
| `counterparty_handle` | VPA, masked account, or masked card |
| `counterparty_name` | as UPI shows it; abbreviated more often at higher difficulty |
| `terminal_id` | `SBX01` Soundbox, `POS01` POS, empty for direct payments |
| `pos_bill_id` | joins `pos_bill_lines.csv` |
| `utr` | 12 digits; unique; matches `disputed_utr` and `utr` in rails events |
| `orig_txn_id` | a refund or reversal → the original transaction |
| `note` | UPI remark, often empty |

`pos_bill_lines.csv` has `pos_bill_id, txn_id, merchant_id, line_no, item, hsn, qty, unit, rate,
line_amount`. Line amounts add up to the transaction amount.

### `visible/rails_events.json`

Every event has `event_id`, `type`, `merchant_id` and `ts`.

| Type | Fields | Notes |
|---|---|---|
| `lien_marked` | `freeze_type`, `scope`, `authority{unit,state,city}`, `ncrp_ack`, `case_ref`, `disputed_amount`, `disputed_date`, `disputed_utr`, `intimation` | The whole account is frozen over one payment. The merchant is not told. |
| `payment_declined` | `direction`, `amount`, `channel`, `counterparty_*`, `reason_code`, `purpose` | Every debit after the lien is declined, retried twice within about 25 minutes. Credits keep landing. |
| `lea_inquiry` | `authority`, `ncrp_ack`, `case_ref`, `amount`, `date`, `utr`, `request`, `confidentiality` | Police ask about one payment with no freeze. **Never message the merchant about it.** |
| `notice_served` | `document`, `photo`, `note` | The merchant photographed a paper notice. Its contents are **only in the document**. |
| `return_filed` | `form` (`CMP-08`), `period`, `declared_turnover` | Composition dealers only |

## Labels (hidden truth)

There are seven true labels. `unclassified` is an answer the agent may give, never a truth.

| Label | Meaning |
|---|---|
| `taxable_supply` / `exempt_supply` | a sale; the side holding most of the basket value wins, and the exact split is in `exempt_value` / `taxable_value` |
| `personal_transfer` | from household family: spouse, sibling, parent, in-law |
| `inter_account` | from an account in the owner's own name, linked or not |
| `non_business` | loan disbursal, chit payout, festival gift from a friend, hand loan repaid, deposit returned, insurance claim |
| `refund_reversal` | a supplier sending part of a payment back, or a failed payout reversed |
| `duplicate` | the refunded twin of a double payment, or the later twin if neither was refunded |

**Aggregate turnover** = taxable + exempt sales (CGST s.2(6)). The threshold is ₹40L for goods and
₹20L for services, and crossing means going strictly above it. A shop selling only exempt goods
need not register (s.23). A fraud-linked credit is still a genuine sale: provenance and fraud
linkage are separate questions.

**Merchant answers** use the tap vocabulary `sale`, `family`, `own_money`, `loan_or_gift`, `refund`,
`double_payment` and `not_sure`. The simulated merchant answers about 93% of questions. They are
occasionally wrong, with rates depending on the label, and sometimes correct themselves 1–20 days
later.

## How a year is made

For each merchant, in this order (`World.build()` in `world.py`):

1. People: owner, two own accounts, four family members, suppliers, a regular-customer pool.
2. Sales. Daily volume comes from day of week, festivals, monthly growth and noise. Each sale is a
   basket of catalogue items, paid by QR, POS (itemised bill) or directly to the VPA.
3. Hard negatives: a customer genuinely buys the same basket again minutes later.
4. Fraud chains: a victim is scammed, the money passes through mules, and the last mule buys
   here. Then a lien, or a police inquiry.
5. Calibration: sales are scaled so turnover crosses the threshold on a pinned date, or lands on a
   target.
6. Double payments (usually refunded, sometimes the wrong twin), family money, non-business money
   and month-start top-ups.
7. **Ledger pass**, in time order:
   - supplier payments, sometimes large stock-ups
   - top-ups from the owner's own accounts when the balance is short
   - supplier refunds and failed-payout reversals
   - Sunday sweeps to savings, and daily balances
   - every debit after a lien is declined
8. Tax notices (the claim is every rupee that came in), CMP-08 returns, the merchant answer
   sheet, and the cues behind each credit.

**The difficulty knob (d = 0 → 1)** controls how often clues appear:
- family: round amounts, off-hours timing, direct payment rather than QR, shared surname, UPI note
- names: how often they are abbreviated ("K GOWDA", "SAHANA G")
- own accounts: whether the second one is linked
- double payments: the gap between them, whether they're refunded, and whether the refund hits the
  wrong twin

The `cues` column in `ground_truth.csv` records which clues each credit actually carries.

## The demo scenario

`hidden/demo_scenario.json` is the answer key. **Read IDs from it; never hard-code them**, because
they change whenever the generator changes. What `sim/scenario.py` pins and asserts on every run:

**Sahana Stores (`MID_DEMO_SAHANA`, Kannada)**
- **Freeze.** A lien lands at 09:30 on Tue 24 Mar 2026 (Cyber Crime PS Hyderabad, NCRP
  `SYN-31703260045812`).
  - The disputed payment is a ₹4,200 POS-billed sale at 19:47 on 21 Mar (onions, potatoes,
    carrots, eggs, rice, tomatoes, beans), paid by a downstream mule.
  - A ₹4,200 decoy on 18 Mar comes from a regular customer. These are the only two ₹4,200 credits
    from 14 to 28 Mar.
  - **339 credits** arrive in the 7 days before the freeze.
  - The morning's supplier payment is declined three times from 09:41.
- **Ordinary Tuesday.** On 10 Mar exactly three credits from 8–9 Mar deserve a question:
  - ₹15,000 at 23:04 from the owner's linked savings account
  - ₹7,500 at 13:20 from the spouse, scanned at the shop QR
  - ₹4,850 from Raghu Shetty, a real sale from someone who bought twice before

  A ₹23 payment from an unknown payer is left alone.
- **Warning.** Turnover crosses ₹40L on **14 Mar 2026**. Replay the projection as of 31 Jan.
- **Notice.** The notice (`SYN/CTD/2026-27/00417`, dated 20 Aug 2026) claims every credit as
  turnover. Sahana did cross ₹40L and must register.
- **Police inquiry.** On 11 Feb 2026, about a ₹1,850 sale on 6 Feb. No freeze, and no message to
  the merchant.

**Maurya Sabzi Bhandar (`MID_DEMO_LKO`, Hindi)**
- Aggregate turnover is about ₹46L, all exempt. It crosses ₹40L in February but need not register.
- A notice (`SYN/ST-LKO/2026-27/01982`, 26 Aug 2026) claims every credit. This is the Haveri
  story.

## Changes from v1

| v1 | v2 |
|---|---|
| One demo merchant, Kannada only | Two demo merchants and six languages across dev and eval |
| Freeze as a single event | A lien event plus the declined payments that follow it, with credits still landing |
| No police inquiries | `lea_inquiry` events with a no-disclosure instruction |
| Notice fields handed over as data | A paper notice as a PDF and phone photo; the fields exist only in the document |
| No devices, balances or settlements | `terminals.json` (device, geo) and `daily_balances.csv` |
| No merchant behaviour | `merchant_answers.csv` and `behaviour.json` for the attestation harness and evidence tiers |
| Eval shops' turnover fell where it fell | Calibrated targets, so the family kiranas sit just under ₹40L |
| Customers could share the owner's exact name | Not allowed, and names are more varied |
| Payer history in the baseline used the whole year | `eval.baseline` uses strictly prior history |

## Caveats

- **This is synthetic.** Distributions are plausible, not calibrated to real Paytm data. Say "on a
  synthetic ledger with known ground truth", never real-world accuracy.
- **Don't tune on eval.** Rules that mirror `world.py` look great and prove nothing. The baseline
  was written by someone who knows the generator, so it is an optimistic floor.
- **Small classes are noisy.** Eval holds only about 50 non-business credits; quote counts with
  percentages.
- **Everything is fictional.** Names, handles, businesses, lenders, chit funds, police and tax
  references (`SYN`) and GSTINs are invented, and the notices are watermarked SYNTHETIC SPECIMEN.
- **Legal points are summarised for engineering.** The aggregate turnover definition, the
  exclusively-exempt rule and the ₹40L/₹20L thresholds need a CA's check before stage (plan §22).
