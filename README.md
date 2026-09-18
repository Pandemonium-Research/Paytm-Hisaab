# Paytm Hisaab

**Every rupee, on your side.**

Hisaab is an autonomous AI teammate for small Paytm merchants. It keeps a tamper-evident
**provenance ledger** of every UPI credit a shop receives, and answers from that ledger when an
authority asks:

- **Freeze.** It finds the one disputed payment among hundreds, builds a graded evidence pack,
  drafts the NCRP/CFCFRMS grievance and sends it to a Paytm officer for approval.
- **Tax notice.** It rebuilds real aggregate turnover with workings, says plainly when the
  merchant *did* cross the threshold, and explains the result to their CA.

> Built for the **Paytm Build for India AI Hackathon** (Bengaluru, Track 3: Autonomous AI
> Teammates, 19 September 2026). All data is synthetic, and every person, business and case
> reference in it is fictional.

**Status: under construction.** Progress is tracked in [PHASES.md](PHASES.md).

## Stack

n8n (the agent workflows, with human approval) · Sarvam AI (sarvam-105b, Saaras, Bulbul,
Translate, Vision) · Cognee (shop memory) · Python/FastAPI · PostgreSQL with pgvector · Twilio
WhatsApp sandbox · a React PWA styled after Paytm for Business.

## Where things are

| Path | What |
|---|---|
| [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) | The design: architecture, ledger, skills, workflows, surfaces, evaluation |
| [PHASES.md](PHASES.md) | The build order, owners and done-when checks |
| [sim/](sim/README.md) | Synthetic world v2: a year of transactions per shop, with hidden ground truth |
| [eval/](eval/) | The rules-only baseline and the scorer |
| [data/](data/README.md) | Generated splits (gitignored) |
| [archive/agent-labs-2026-09-12/](archive/agent-labs-2026-09-12/) | The earlier Agent Labs build. Kept for reference, never imported |

## Local quickstart

```bash
python tasks.py up
curl http://localhost:8080/api/healthz
open http://localhost:8080/api/docs       # use start on Windows
python tasks.py test
```

The default stack starts PostgreSQL with pgvector, core, the provider fakes and Caddy. Memory
and web are declared under the `surfaces` profile because Lane B owns their Dockerfiles. Add
`--surfaces` once those exist, and add `--local-n8n` for the pinned local n8n fallback. Until
the web service lands, `/` and `/mem/*` correctly return 502 while `/api/*` remains available.

For a phone, run `python tasks.py tunnel` in one terminal. It always uses HTTP/2. Then run
`python tasks.py publish` in another terminal to write the captured hostname into core's
runtime config. It does not contact n8n Cloud or Twilio. Only `python tasks.py --live publish`
loads `.env.live` and updates those remote settings, and it refuses unless that file sets
`HISAAB_LIVE=1`.

Simulator generation remains available through the same runner:

```bash
python tasks.py generate                 # all four splits, about 30 s
python tasks.py generate --only demo
```

Then the rules-only baseline and its score on the eval split, which need no stack:

```bash
python -m eval.baseline data/eval
python -m eval.score data/eval data/eval/predictions_baseline.csv
```

## Two rules for contributors

- **Product code never reads `data/<split>/hidden/`.** Only `sim/` and `eval/` may.
- **No credits during development.** Build and test against the local n8n and the fakes; real
  keys live only in `.env.live` (gitignored) and are used only in the budgeted live windows
  (plan §16a).

## Licence

No licence file has been added yet.
