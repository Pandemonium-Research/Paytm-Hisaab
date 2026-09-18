# Lanes: who builds what

Two people, two lanes that don't overlap. Every task in [PHASES.md](PHASES.md) and every folder
in the repo has exactly one owner, so you can both work at full speed on `bfi` without
waiting for each other or editing the same files.

**A = Ledger and skills:** core API, database, skills, fakes, data, eval, infra.
**B = Agent and surfaces:** n8n workflows, Sarvam, Cognee, WhatsApp, the PWA, prompts, legal.

**Who takes which lane.** B runs the live checks (L1) and needs `.env.live`, the n8n Cloud
login and the two phones joined to the Twilio sandbox. A never needs a real key: everything A
builds runs on the fakes. So the person with the demo laptop takes **B**.

---

## 1. What each person owns

Only the owner edits these paths. If you need a change in the other person's area, ask; don't
edit it yourself.

| Path | Owner |
|---|---|
| `services/core/**` (except `app/schemas/llm.py`) | A |
| `services/fakes/**` (except `cassettes/`) | A |
| `sim/**`, `eval/**` | A |
| `docker-compose.yml`, `Caddyfile`, `tasks.py`, `.env.example`, `README.md` | A |
| `services/core/app/schemas/llm.py` (LLM output schemas) | B |
| `services/fakes/cassettes/**` (recorded in the L1 window) | B |
| `services/memory/**` | B |
| `services/web/**`, `design/**` | B |
| `n8n/**` (workflows, the workflow table, spike results, `n8n/cli.py` for export and import) | B |
| `prompts/**`, `i18n/**`, `legal/**` | B |
| `IMPLEMENTATION_PLAN.md` | both, changed only by agreement |
| `PHASES.md`, `LANES.md` | each ticks only their own boxes |

- **Compose already wires in B's services.** A's `docker-compose.yml` includes entries for
  `memory`, `web` and the `local-n8n` profile from 2A.1. B owns the Dockerfiles behind them.
- **`tasks.py` calls into B's code.** A adds one-line commands that call `n8n/cli.py` (for
  `export-n8n` and `import-n8n`) and the web app's Playwright runner (for `e2e`).
- **B's services reach core through its API.** The memory service reports Cognee usage to
  core through `POST /ops/usage` (A, 2F.5), and never writes to the database directly.

## 2. Rules for working in parallel

- **One branch, small commits.** Everything goes on `bfi`, with the task ID in each message.
  Run `git pull --rebase` before every push, and push after every task.
- **Never wait.** Build against core's stubs (2A.7) and the fakes (2F). If a handoff is late,
  carry on down your queue and swap in the real thing when it arrives.
- **Contracts are frozen after Phase 1.** Any change to `services/core/app/schemas/*` or to the
  workflow table in `n8n/README.md` needs the other person's OK in chat first.
- **Each person runs their own local stack:** copy `.env.example` to `.env`, then run
  `python tasks.py up`. It needs no keys and spends no credits.
- **Live windows run only on the demo laptop,** where `.env.live` lives. Never copy that file
  anywhere else, or paste a key into chat.
- **Checkpoints:** one person drives each one (§5). If it fails, the owner of the broken part
  fixes it, and the other person carries on down their queue.

## 3. Handoffs, in the order they happen

| # | From → to | What | What is blocked until then |
|---|---|---|---|
| H1 | both | Phase 1 signed off | everything |
| H2 | A → B | Stack up: compose, Caddy, tunnel, core stubs (2A.1, 2A.2, 2A.7) | B's workflows calling core; S7, S8 |
| H3 | A → B | Minimal fakes (Twilio Messages API and media URLs, Sarvam chat) and `fake-wa` (part of 2F.1, then 2F.6) | 2C.1, WF30 and WF31 on the local n8n |
| H4 | A → B | The recorder (2F.2) | The L1 live window (2B) |
| H5 | B → A | L1 cassettes committed | Fakes replaying STT, TTS, translation and Vision |
| H6 | A → B | Phase 4 endpoints real, not stubs (4.6–4.8, 4.11) | CP1 |
| H7 | B → A | WF10 seed mode works (5.7) | Seeding the year (8.5) |
| H8 | A → B | Freeze detector and approvals (6.9, 6.10), then packs (6.8) | WF20 end to end |
| H9 | B → A | `legal/citations.yaml` with verified flags (2L) | Citations guard and grievance template (6.6, 6.7) |
| H10 | B → A | Refusals (9.2) and WF21 (9.11) | `beats` check B6 (8.7) |
| H11 | A → B | Anchors (8.4) | WF60 (9.7) |

## 4. The queues

Work top to bottom. **→ Hn** means "this step completes handoff Hn: tell the other person".
**Needs Hn** means "swap in the real thing once Hn arrives; build against stubs until then".

### Lane A

1. **Phase 1 draft:** 1.1 ledger entry kinds, 1.2 role matrix, 1.3 endpoint list. Include the
   cassette format for 2F.2, so B's L1 recordings fit the fakes.
2. **Unblock B first:**
   - 2A.1 compose and `tasks.py`, with `generate` (3.17)
   - 2A.2 Caddy and the tunnel
   - 2A.7 stubs → **H2**
   - 2F.1, minimal (Twilio and Sarvam chat), then 2F.6 `fake-wa` → **H3**
   - 2F.2 recorder and replay → **H4**
3. **Ledger core:** 2A.3, 2A.4, 2A.5, 2A.6, then 2A.8 with the `hidden/` grep test (3.18).
4. **Credit guard:**
   - 2F.3, the `HISAAB_LIVE` switch in core's provider clients
   - 2F.4, pytest's socket guard
   - 2F.5, the usage table and `POST /ops/usage`
   - the rest of 2F.1 (STT, TTS, translation, Vision), replaying the L1 cassettes (needs H5)
5. **Phase 4:** 4.1 to 4.12, in order → **H6**. Then **CP1**.
6. **Phase 6:**
   - 6.9 and 6.10 first → **H8**
   - then 6.1–6.5 and 6.8 (the rest of H8), 6.6 and 6.7 (needs H9), 6.11, 6.12
   - Then **CP2**.
7. **Phase 8, P0:** 8.1, 8.2, 8.3, 8.5 (needs H7), 8.6, 8.7 (needs H10).
8. **Phase 8, P1:** 8.4 → **H11**, then 9.12a (the push endpoint in core), 3.21, and 8.8
   (live window L3, optional).
9. **CP3, A's part:** 10.1, 10.1b-A (tunnel, `publish`, `beats --live`, the live demo seed,
   `usage`), 10.3, 10.4b, 10.5.
10. **P2, only if CP3 is green:** 11.1, 11.5, 11.6.
11. **Saturday:**
    - 12.1, 12.4 (fallback video), 12.5
    - 12.6 with 3.19 (the deck and README numbers)
    - 12.9 (tag, then merge `bfi` into `main`)
    - 12.11, 12.12-A (laptop, tunnel, `publish`)

### Lane B

1. **Phase 1 draft:** 1.4 LLM output schemas (in `schemas/llm.py`), 1.5 the workflow table
   and webhook payloads (in `n8n/README.md`), 1.6 screens mapped to read models, 1.7 i18n keys.
2. **Needs nothing from A:**
   - 2D.1–2D.4, with the fonts self-hosted
   - 2C.4, the numbered-reply format
   - 5.1, the memory service: stub backend first, then self-hosted, with its own `HISAAB_LIVE`
     switch
   - 5.3, prompts v1
   - 2L, legal research: finish it before A reaches 6.6 → **H9**
3. **Needs H2 and H3:** 5.2 local n8n credentials, 2C.1, 5.5 WF30, 5.6 WF31, tested on the
   local n8n with `fake-wa`.
4. **Needs H4. Live window L1, on the demo laptop:** S1–S8, 2C.2, 2C.3 and the one batched
   translation, all recorded → **H5**. Then 5.4 i18n files, from the cassette.
5. **Before CP1:**
   - 5.7 WF10: seed mode first → **H7**, then live mode
   - 5.8 screens M0, M1, M2, M6
   - 2D.5 the PWA installed on a phone through the tunnel
   - Then **CP1**.
6. **Phase 7:** 7.1, 7.2, 7.3, 7.4 (needs H8), 7.5, 7.6, 7.7, 7.8. Then **CP2**.
7. **Phase 9, P0:**
   - 9.1 `/demo`
   - 9.2 refusals (part of **H10**)
   - 9.3 Playwright, blocking external requests (the web half of 2F.4)
   - 8.9 the `/ledger` and `/eval` pages
8. **Phase 9, P1, in order:**
   - 9.4, 9.5, 9.6
   - 9.7 (needs H11)
   - 9.8, 9.9, 9.10
   - 9.11 (the rest of **H10**)
   - 9.12b (service worker and UI)
   - 9.13
9. **CP3, B's part:** 10.1b-B (import the workflows into n8n Cloud and create its credentials),
   10.2, 10.4, 10.6.
10. **P2, only if CP3 is green:** 11.2, 11.3, 11.4.
11. **Saturday:** 12.3, 12.7, 12.8, 12.12-B (phones, Twilio join).

## 5. Joint moments

These are sync points, not shared work.

| When | What | Driver |
|---|---|---|
| Start | Phase 1 sign-off: swap drafts and spend 15 min each reviewing the other's | both |
| CP1 | Ordinary Tuesday on the local n8n and the fakes | B |
| CP2 | Freeze on the local n8n and the fakes | A |
| CP3 | Integration, and the first live pass (L2) | A (B imports the workflows into n8n Cloud) |
| Saturday | Rehearsals (12.2), feature freeze (12.10), the demo | both |

## 6. Timing

The plan's clock times assumed a Thursday-evening start. You're starting Phase 1 at about
13:00 on Friday, which is when CP1 was due. The planned work from Phase 1 to CP3 adds up to
roughly 24 hours, so at the planned pace CP3 lands around midday Saturday.

Agree new checkpoint times at the Phase 1 sign-off, and cut early rather than late:

- **Cut first:** the whole P1 block (3.21, 8.4, 8.8, 9.4–9.13) and all of Phase 11.
- **Then simplify:**
  - 2F.2: save the L1 responses as fixtures by hand instead of building a recording proxy
  - 2D.1: two or three reference screenshots, not ten
- **Never cut:** P0, the tests covering P0, or the credit rule.
