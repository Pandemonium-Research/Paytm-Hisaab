# DEPLOY.md — putting the data service on Render

The Phinite sandbox cannot read our CSVs, so every tool call goes over HTTPS to this
service. Track A is blocked until the URL exists. Companion to
[BUILD_PLAN.md](BUILD_PLAN.md) (§ Data service) and [PLAN.md](PLAN.md).

Fifteen minutes, most of it Render's first build.

## Before you start

- The repo is pushed to `git@github.com:Pandemonium-Research/Paytm-Hisaab.git`.
- A Render account with that GitHub org authorised (Render → Account → GitHub →
  **Configure account** → grant access to `Pandemonium-Research`).
- The two service keys. Generate a fresh pair with:

  ```
  python -c "import secrets; print('read  ', secrets.token_urlsafe(24)); print('attest', secrets.token_urlsafe(24))"
  ```

  Keep them out of git. They are set in the Render dashboard, not in `render.yaml`.

## 1. Create the service

Render Dashboard → **New** → **Blueprint** → pick `Pandemonium-Research/Paytm-Hisaab`
→ branch `main` → **Connect**.

Render reads [render.yaml](render.yaml) and finds one web service, `hisaab-data-service`.
It will prompt for the two values marked `sync: false`:

| Key | Value | Goes on |
|---|---|---|
| `HISAAB_KEY` | your read key | **both** graphs |
| `HISAAB_ATTEST_KEY` | your attest key | **only** `hisaab-merchant` |

Paste them and **Apply**. Everything else — Python version, split, ledger path — is in
the blueprint already.

### What the build does

```
pip install -r requirements.txt          # fastapi + uvicorn, nothing else
python -m synth.generate --only demo     # ~1 min: regenerates data/demo from fixed seeds
python -m tools.simulate_year --reset    # seeds a year of proposals into ledger.db
```

No data is committed, so the txn_ids in DATA.md are reproduced from the seed on every
build. The third step is what makes the demo work on arrival: without it the ledger is
empty and beat 1 has no queue to show. Expect it to print

```
asked the merchant     189 over 149 days (median 1.3/day, 0 beyond the daily budget)
still untagged         0 credits
```

If those numbers differ from [BUILD_PLAN.md](BUILD_PLAN.md), the data changed — stop and
check before demoing, because the answer key in `data/demo/hidden/` moved with it.

First build is 3–5 minutes. Watch **Logs**; it ends with uvicorn on `0.0.0.0:$PORT` and
the health check going green.

## 2. Verify before handing it over

Copy the URL from the top of the service page — `https://hisaab-data-service.onrender.com`
or similar. Then, from any terminal:

```bash
URL=https://hisaab-data-service-xxxx.onrender.com
KEY=<your read key>

curl -s $URL/health
```

`/health` is deliberately unauthenticated so Render's health check can reach it. Expect
`"ok": true`, `"split": "demo"`, ~13,000 transactions, a non-zero `ledger_rows`, and
`"auth": "keyed"`. **If `auth` says `open`, the keys did not get set** — the service is
serving the whole ledger to anyone who finds it. Fix that before sharing the URL.

Four checks worth running, in this order:

```bash
# 1. the key is actually enforced
curl -s -o /dev/null -w "%{http_code}\n" $URL/merchants                     # 401
curl -s -o /dev/null -w "%{http_code}\n" -H "X-Hisaab-Key: $KEY" $URL/merchants   # 200

# 2. the ledger was seeded — beat 1 has something to ask about
curl -s -H "X-Hisaab-Key: $KEY" \
  "$URL/attestation_queue?merchant_id=MID_DEMO_SAHANA&date=2026-03-10&lookback_days=2&max=3"

# 3. the read key cannot attest (this is the permission boundary the pitch rests on)
curl -s -o /dev/null -w "%{http_code}\n" -X POST $URL/ledger/attest \
  -H "X-Hisaab-Key: $KEY" -H "Content-Type: application/json" \
  -d '{"txn_id":"x","label":"taxable_supply"}'                              # 403

# 4. beat 4's disputed credit is there
curl -s -H "X-Hisaab-Key: $KEY" $URL/credits/by_utr/608019013171
```

Check 2 must return three rows. Check 3 must be **403** — if it returns 404 or 200, the
attest key is missing or the same as the read key, and the demo's best line ("the agent
that watches cannot sign on her behalf") is not true.

Then point the local harness at the deployed service and run the beats against it:

```bash
HISAAB_API=$URL HISAAB_KEY=$KEY python -m tools.check_beats
```

All four should pass exactly as they do locally. This is the real acceptance test — it
exercises the same tool code Phinite will run, over the same network path.

## 3. Hand over to Track A

Send your teammate exactly this, and nothing more:

```
HISAAB_API         = https://hisaab-data-service-xxxx.onrender.com
HISAAB_KEY         = <read key>        → set on BOTH graphs
HISAAB_ATTEST_KEY  = <attest key>      → set ONLY on hisaab-merchant
```

In Phinite these go in **Settings → Environment variables**, per environment (DEV, UAT,
PROD each need their own copy). Tools read them as `env_variables["HISAAB_API"]` etc.

Putting `HISAAB_ATTEST_KEY` on `hisaab-watch` would let the nightly pass commit
attestations in the merchant's name. The tool policy in BUILD_PLAN.md denies
`commit_attestation` to Provenance; the split key is the second lock on the same door.
Both have to hold, or neither claim is true.

Smoke test from Track A's side: publish `get_credit`, run it in Dev Studio with
`txn_id` from `phinite/TOOL_SCHEMAS.md` §1. A row back means the whole pipeline —
Phinite sandbox → Render → SQLite → tool → trace — is live.

## 4. Free-plan caveats

**It sleeps after 15 minutes of inactivity.** The next request takes ~50 seconds to wake
it, which will look like a hung agent on stage and may blow Phinite's tool timeout. Two
fixes, pick one:

- **Keep it warm** (free): a cron pinger — [cron-job.org](https://cron-job.org) or
  UptimeRobot — hitting `$URL/health` every 10 minutes. Set this up the night before,
  not on the morning.
- **Upgrade to Starter** ($7/month, cancel after): no sleeping, and the demo stops
  depending on a pinger you cannot see. Worth it for a single day.

Either way, **hit the URL yourself 5 minutes before going on stage.**

**The filesystem resets on restart.** Attestations committed during the demo are lost
when the instance sleeps — the ledger reverts to the build-time seed. For the demo this
is a feature: sleeping restores the 8–9 Mar queue that beat 1 needs, so a rehearsal
cannot spend it. But it means nothing you attest is durable. Attach a persistent disk
only if that matters, which for one day it does not.

**Rehearsing spends the queue.** If a run-through attests the three credits beat 1 asks
about, they are gone until the next restart. To reset deliberately, Render →
**Manual Deploy** → **Clear build cache & deploy**, which re-runs the seed (3–5 min), or
locally `python -m tools.simulate_year --reset`.

## 5. Fallback if Render will not cooperate

Run the service locally and tunnel it:

```bash
python -m uvicorn service.app:app --port 8000
ngrok http 8000          # or: cloudflared tunnel --url http://localhost:8000
```

Put the tunnel URL in `HISAAB_API` and set the same two keys as real environment
variables before starting uvicorn — with neither key set, auth falls open. The URL
changes every time ngrok restarts, so Phinite's env vars have to be re-entered; treat
this as the backup, not the plan.

## Troubleshooting

| Symptom | Cause |
|---|---|
| Build fails in `synth.generate` | Python version. The blueprint pins 3.12.7; the code needs ≥3.10 for `str \| None` annotations. |
| `/health` says `"auth": "open"` | Neither key reached the environment. Render → Environment → check both, then redeploy. |
| `"ledger_rows": 0` | The seed step did not run or failed silently. Check the build log for the `asked the merchant` line. |
| `/attestation_queue` returns nothing | Either the ledger is empty, or a rehearsal already attested them. Re-seed. |
| Tools 500 with `no transaction …` | Wrong split. `HISAAB_SPLIT` must be `demo`; the IDs in DATA.md are demo-split IDs. |
| Phinite tool times out on first call | The instance was asleep. See §4. |
| `404` on `/merchant_mix` or `/untagged` | Render is running an older commit. Check the deploy's commit SHA against `main`. |
