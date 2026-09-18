# n8n

Workflow JSON lives in `workflows/`, one file per workflow, exported with
`python tasks.py export-n8n --target cloud|local`. The design is in
[IMPLEMENTATION_PLAN.md](../IMPLEMENTATION_PLAN.md) §10.

## Instance (task 0.1, checked 18 Sep 2026)

| Item | Value | Source |
|---|---|---|
| Plan | n8n Cloud **Pro**, from the hackathon voucher, for one month | voucher |
| Executions | **10,000 a month.** An execution is one run of a whole workflow, however many steps. Over the quota, workflows keep running but "overage charges may apply". | [pricing](https://n8n.io/pricing/) |
| Concurrency | **20 production executions** (started by a webhook or trigger). Extra ones queue and run first in, first out. Manual, sub-workflow and error executions don't count. | [Understand concurrency](https://docs.n8n.io/deploy/use-n8n-cloud/understand-concurrency.md) |
| Execution log retention | 7 days | pricing |
| Test evaluations | One test case at a time on Pro | Understand concurrency |
| Public API | Included on Pro (not on the trial). Header `X-N8N-API-KEY`, base `https://<name>.app.n8n.cloud/api/v1`. Below Enterprise there are no scopes, so the key has full access to the instance. **Checked:** `GET /api/v1/workflows` returned 200 on 18 Sep. | [Authentication](https://docs.n8n.io/connect/n8n-api/authentication.md) |
| API key | Created 18 Sep 2026, **expires 16 Dec 2026**; stored in `.env.live` only | read from the key |
| Instance URL | `https://pandemonium-research.app.n8n.cloud` (`N8N_BASE_URL`) | |
| Instance version | *To read in the editor under Help → About n8n. The API doesn't expose it. Human review of AI tool calls needs 2.6 or later (§10).* | |

## What this means for the build

- **Executions aren't the constraint.** The live-window budget in §16a is 135 executions in
  total, about 1.4% of the month. Keep to it anyway, so the voucher never runs into overage.
- **Twilio must call the production URL** (`/webhook/...`), which exists only while the
  workflow is published. The test URL (`/webhook-test/...`) listens only while the editor is
  waiting for a test event.
- **Twilio can't send custom headers.** WF31's webhook therefore uses no n8n auth and checks
  `X-Twilio-Signature` in its first Code node. Webhooks that core calls use Header Auth with
  `N8N_WEBHOOK_SECRET`.
- **Answer Twilio at once** (response mode "Immediately") and send the reply through the
  Messages API from WF30. Twilio gives up on a webhook after 15 s, and a Sarvam call plus the
  guards can take longer.
- **The webhook payload limit is 16 MB.** Twilio sends media as URLs, so this only matters for
  uploads from the app, which go to core, not to n8n.
- **WF10-eval (9.9) runs its ~50 cases one after another**, because Pro evaluates one test case
  at a time.
- **Execution logs last 7 days.** Screenshots and exports for the n8n prize (12.8) come from the
  L2, L4 and L5 runs, all inside that window.

## Credentials to create

Local n8n (development, task 5.2): one HTTP Header Auth per role key, plus Sarvam and Twilio
pointed at `FAKES_URL`. n8n Cloud (live, task 10.1b): the same set with the real keys from
`.env.live`.

## Workflows (task 1.5)

*To be filled in during Phase 1: ID, trigger, inputs and outputs, role key, webhook payloads.*

## Spike results (2B, window L1)

*One line per check S1–S8: go or no-go, and the fallback chosen if it failed.*
