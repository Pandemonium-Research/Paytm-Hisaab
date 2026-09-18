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

**Status: under construction.** The active prototype queue and handoffs are in
[PROTOTYPE_STATUS.md](PROTOTYPE_STATUS.md); the full backlog is in [PHASES.md](PHASES.md).

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
python tasks.py migrate
curl http://localhost:8080/api/healthz
open http://localhost:8080/api/docs       # use start on Windows
python tasks.py test
python tasks.py test --postgres          # trigger, grants, tamper and concurrency checks
```

The default stack starts PostgreSQL with pgvector, core, the provider fakes and Caddy. Memory
and web are declared under the `surfaces` profile because Lane B owns their Dockerfiles. Add
`--surfaces` once those exist, and add `--local-n8n` for the pinned local n8n fallback. Until
the web service lands, `/` and `/mem/*` correctly return 502 while `/api/*` remains available.

`migrate` provisions `hisaab_owner` and `hisaab_app`, then runs Alembic as the owner. The API
connects as `hisaab_app`, which can only insert and read ledger entries. It can update chain
heads and operational state. Both roles are stopped by the ledger's mutation triggers;
only the owner can deliberately disable one. `test --postgres` prepares a separate
`hisaab_ledger_test` database, so the tamper and truncate checks cannot affect demo data.

Payment ingestion, visible-data replay, proposals, questions, claims, rules, question selection
and merchant/payment/history reads now use Postgres. Home and Confirm reads reflect saved answers.
Assistant inbound forwards to local WF31 and outbound messages persist. Assistant SSE, cases,
evidence/approval, turnover and reset remain fixtures; see the active queue.

For B's local workflows:

```bash
python tasks.py up --local-n8n
python tasks.py import-n8n --target local --activate
```

`import-n8n` and `export-n8n` call B's `n8n/cli.py`. A Cloud target requires `--live` and
`HISAAB_LIVE=1`. The local n8n reads the same fake Twilio token as `fake-wa` (default `fake`),
and permits environment access inside nodes. Cloud configuration remains an S5/S8 check.

For a phone, run `python tasks.py tunnel` in one terminal. It always uses HTTP/2. Then run
`python tasks.py publish` in another terminal to write the captured hostname into core's
runtime config. It does not contact n8n Cloud or Twilio. Only `python tasks.py --live publish`
loads `.env.live` and updates those remote settings, and it refuses unless that file sets
`HISAAB_LIVE=1`.

Simulator generation remains available through the same runner:

```bash
python tasks.py generate                 # all four splits, about 30 s
python tasks.py generate --only demo --force
python tasks.py replay --split demo --until 2026-03-10T02:00:00+05:30
curl -H "X-Hisaab-Key: dev-app" \
  "http://localhost:8080/api/app/home?merchant=MID_DEMO_SAHANA"
```

Once the data is loaded, save that starting point so a rehearsal can be run more than once:

```bash
python tasks.py snapshot                 # about 4 s
python tasks.py reset                    # about 36 s; discards everything since the snapshot
```

Take the snapshot **straight after `replay`, before any workflow run.** The ledger refuses
UPDATE, DELETE and TRUNCATE, so a run that labels the demo credits cannot be undone in place, and
WF10 skips credits that already carry a machine label: one interrupted run can leave a database
that will never select three questions again. `reset` stops n8n, restores the dump and restarts
core; add `--local-n8n` to bring n8n back up with it.

Replay uses only `visible/`, saves complete bills and observed credits, and sets the persistent
business clock. Repeating it is safe. It loads payments without running WF10 or answering questions.
For the first demo load it can take a few minutes. Workflow writes must use `home.as_of` rather
than the wall clock; advance `/sim/clock` before writing at a later demo time.

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
