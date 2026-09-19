# Demo day runbook

One public URL, three acts, about eight minutes. Everything below is driven from that URL
except the reset, which has to run in a terminal on this laptop.

## Before you start

```bash
python tasks.py up                      # all six containers
python tasks.py reset --name demo --local-n8n
python tasks.py tunnel                  # prints the public URL
```

`reset` restores the snapshot: business clock 10 March 2026 02:00 IST, 36,827 payments
loaded, **zero** labels, questions and cases. That empty starting point is the demo.

Then wait for n8n. It reports healthy roughly 5–15 seconds before its webhooks register,
and a nightly triggered in that gap returns 404. The Demo remote's n8n dot going green is
necessary, not sufficient — give it another fifteen seconds.

Check the three screens load before anyone is watching:

| Screen | Path | What it is |
|---|---|---|
| Merchant | `/merchant` | Sahana's phone |
| Officer | `/officer` | the reviewing officer |
| Demo remote | `/demo` | your control panel — keep this on your own phone |

## Act 1 — the night run finds what needs asking

1. Open `/merchant`. It is quiet: no turnover, nothing to confirm. Say that 36,827 payments
   have arrived and not one of them is classified yet.
2. On `/demo`, tap **Run nightly**. It takes about 55 seconds; the button locks for three
   minutes afterwards so two runs cannot overlap.
3. While it runs, say what it is doing: every unlabelled payment in the window goes through
   the deterministic rules, and only the ones the rules cannot settle go to the model.
4. Reload `/merchant`. It now reads **68 transactions classified, 96% automatically, 3
   awaiting confirmation** — and a turnover card against the ₹40,00,000 threshold.

The number that matters is 96%. The merchant is asked about three payments, not 68.

## Act 2 — the merchant answers, in her own language

1. Tap **Confirm payments**. Three questions, in Kannada, each naming the payer and amount.
2. Switch the language picker to English, then Hindi. The same question, the same three
   payments — the strings come from catalogues, not from the model.
3. Answer one: ₹15,000 from SAHANA GOWDA is **My own money**. Answer the ₹7,500 as a sale.
4. Go back Home. The awaiting count drops and the turnover figure moves.

Say what just happened: her answer is recorded *beside* the machine's label, not over it.
Both stay in the chain, and if they disagree the disagreement is part of the evidence.

## Act 3 — the freeze, and the pack

1. On `/demo`, tap **Start declines and lien**. Cards start declining, then the bank marks a
   lien. A case opens on its own.
2. `/merchant` shows **Payments on hold** with a progress tracker.
3. Open `/officer`. The evidence pack is there: every disputed rupee with the tier of
   evidence behind it — a bill, a rule, her answer, or something added after the notice.
4. Approve it. The merchant's tracker advances to *sent to bank and police*.

The line to land: the pack was not written after the freeze. It was accumulating every
night for months, which is the only reason it can say *this* rupee is backed by *that* bill.

## Ask Hisaab

The **Ask Hisaab** card on Home opens the assistant. Type a question; the workflow answers
and both sides are stored. This is the in-app stand-in for WhatsApp — the same n8n workflow
serves both, so what you are showing is the real path, not a mock of it.

WhatsApp itself is not in this demo: the Twilio account requires approved Content Templates
for every business-initiated message and has none, so sends return 21654. Say that plainly
if asked — the integration is wired, the account is not provisioned.

## Running it again

```bash
python tasks.py reset --name demo --local-n8n
```

Then wait for n8n's webhooks again. Do **not** skip the reset: WF10 skips credits that
already carry a label, so a second nightly on the same database produces zero questions and
Act 1 shows nothing. The ledger refuses UPDATE and DELETE, so restoring the snapshot is the
only way back.

## If something breaks

| Symptom | Cause | Fix |
|---|---|---|
| Nightly returns 404 | webhooks not registered yet | wait 15s, tap again |
| Nightly runs, 0 questions | database not reset | run the reset, wait, retry |
| Nightly 422 in the n8n log | clock behind the run's `as_of` | `POST /sim/clock` to 2026-03-10T02:00:00+05:30, then re-cut the snapshot |
| n8n dot red, "failed to fetch" | n8n container down | `docker compose up -d n8n`, wait for healthy |
| Screens load, buttons do nothing | core running a stale image | `docker compose build core && docker compose up -d core` |
| Tunnel URL dead | quick tunnel dropped | `python tasks.py tunnel` again — **the URL changes** |

The tunnel URL is not stable across restarts. Re-share it if you restart the tunnel.
