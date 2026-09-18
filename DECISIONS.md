# Decisions

Every decision we settle in discussion, recorded when it is made. The plan
([IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)) says what we set out to build; this file says
where we changed course, and why. Newest last. Both lanes append here.

**Status:** *done* is in the code; *agreed* is settled but not yet built.
**Contract decisions** (anything in `services/core/app/schemas/` or the n8n workflow table) need
both people, per [LANES.md](LANES.md) §2.

---

## Contracts (Phase 1)

| # | Decision | Why | Agreed | Status |
|---|---|---|---|---|
| D1 | **Money is `int`, whole rupees**, everywhere. Only `/app/*` read models add a preformatted display string beside it. | `sim/` is already built in whole rupees (`THRESHOLDS = 4_000_000`). Paise would have put every turnover figure out by 100×. | A | done |
| D2 | **Label and answer vocabularies come from `sim/catalog.py`**, and a test fails if core's enums drift from `PREDICTION_LABELS` or `ANSWER_CHOICES`. | The synthetic world is committed; a second, hand-written vocabulary would silently diverge from the data every accuracy number is measured on. | A | done |
| D3 | **`recorded_at` never appears on a request model.** A test walks every request model to enforce it. | It is the database's `clock_timestamp()`. A caller who can supply it can backdate evidence. | A | done |
| D4 | **Agent confidence is capped at 0.85** by a validator, not a comment. Rule-derived labels may be 1.0. | §7. A comment does not stop an agent from claiming certainty. | A | done |
| D5 | **The role matrix is data** (`ROLE_ENTRY_KINDS`, `ENDPOINT_PERMISSIONS`), imported by `auth.py` and the permission tests. | One source of truth for §14, so the rules and the tests cannot disagree. | A | done |
| D6 | **`anchor.created` belongs to `admin`.** | §6 names an "anchor job" that §14 gives no role, so nobody could append it. WF60 reaches it through `POST /anchors/run`, which §7 limits to admin. | A | done |
| D7 | **Question ordering:** priority (`amount × (1 − confidence) × proximity`) picks the day's three; those three are then asked least confident first. | The plan's two orderings looked contradictory but act at different stages. | A | done |
| D8 | **Guards and prompts follow §7's per-endpoint grants** where §14's "May call" column is silent. | §7 is the more specific of the two. | A | done |
| D9 | **`POST /rails/debits` is added.** `/rails/credits` goes back to credits only. | §6 has a `rails.debits` table and the simulator emits debits, but §7 gave them no endpoint. The freeze case is built on declined debits. | A, B | done |
| D10 | **A seventh role, `app`, with no append rights at all.** The merchant PWA uses it for `/app/*`, `POST /assistant/inbound` and `GET /assistant/stream`. `POST /assistant/outbound` stays `conversation`. | The app key ships to a browser. Mapped to `conversation`, anyone with devtools could append claims. The app never needs to: inbound forwards to n8n, which writes to the ledger server-side. It also makes the WF99 refusal demo concrete. | A, user | done |
| D11 | **`GET /app/questions`** feeds screen M2, one card per question. Its chips are a 5-item subset of `AnswerChoice`. | Gap G1 (B). `/app/home` carries only a count. CP1 check 2 needs three questions in M2, so CP1 could not pass without it. | A, B | done |
| D12 | **`PUT /app/profile`** saves M0's language and consent as ops state, with `consent_at`, `language` and `consent_text_version`. **No ledger kind for consent.** | Gap G2 (B). The plan frames consent only as the M0 promise ("at most 3 questions a day"); §22 has no consent item and no DPDP reference, so it is not evidence about a credit. The text version shows which wording was agreed to, in which language. | A, B | done |
| D13 | **`GET /app/officer/outbox`** feeds O3, with freeze→pack and pack→approval **computed in core** as durations. | Gap G3 (B). If the front end subtracts timestamps, the figure on O3 and the one in the evidence pack can drift apart. | A, B | done |
| D14 | **One answer enum: `AnswerChoice`**, 7 values, canonical in `app/schemas/common.py`. B's `MerchantAnswer` in `llm.py` is replaced by an import of it (for `IntentSlots.answer`). What each channel shows is a subset: WhatsApp numbers 4 (§11), M2 chips 5 (§12.2), voice or free text can reach all 7. | Two enums for the same thing would drift. | A, B | done |
| D15 | **`claim.answered` records the answer, not a label.** It carries `answer: AnswerChoice`; `current_view` resolves it to a label. A `sale` answer takes the machine's supply label, decided by the bill or the shop's billed exempt share. | Supersedes the interim fix in `8764a53`, which stored both and required a label. A merchant can confirm it was a sale but cannot say which tax class it is in, so any stored label would have been our guess recorded as their claim. `ANSWER_TO_LABELS` stays as the resolution map. | A, B | done |
| D16 | **Merchant app and officer app are callers, not roles.** Merchant app uses `app` (D10); officer app uses `officer`. | §7 names them as callers, but §14's role vocabulary has neither. | A | superseded in part by D10 |
| D23 | **B writes the B sections of `services/core/CONTRACTS.md` directly**, under a `## Lane B` heading at the end. An exception to LANES §1 for this one file. | One file to sign off from, and B's content is B's to write; A transcribing it risks misstating it. Appending at the end keeps B's edits clear of A's, so the two merge cleanly. | A | agreed |
| D24 | **2C.4 numbered-reply format is the plan's four options:** 1 sale · 2 family · 3 my own money · 4 not sure. Each maps to an `AnswerChoice`. | Confirms the WhatsApp subset in D14. | A, B | agreed |
| D28 | **Merchant-scoped reads take `?merchant=`**, declared in the contract, including every merchant `/app/*` screen, `PUT /app/profile` and `GET /assistant/stream`. Officer screens stay cross-merchant. | The shared `app` key carries no merchant identity, so `/app/home` could not know whose home it was. §7's other reads already use `?merchant&as_of`, but no GET declared its query parameters, so none of them showed on `/api/docs`, which is what B builds n8n nodes from. | A | done |
| D29 | **The `app` key does not get `/guards/*` or `/prompts/{name}`.** It keeps `GET /config`. | §7 grants those to "all", which was coded as every role and so picked up `app` automatically. The app never calls a guard (n8n does), and `/prompts` would hand the prompt text to anyone with devtools. D10 is least privilege for the one key that ships to a browser. | A | done |

## Infrastructure (2A)

| # | Decision | Why | Agreed | Status |
|---|---|---|---|---|
| D17 | **`tasks.py` uses only the standard library** (`argparse`), not `invoke`. | It has to run on a fresh clone, on macOS and Windows, before any `pip install`. Every usage in the plan is already `python tasks.py …`. | A | done |
| D18 | **Postgres is `pgvector/pgvector:pg16`; Caddy is `caddy:2.10-alpine`; local n8n is `n8nio/n8n:2.39.7`.** | n8n matches the Cloud instance (0.1). The plan pinned neither of the others. | A | done |
| D19 | **B's services sit behind a compose profile (`surfaces`)**, so `tasks.py up` works before their Dockerfiles exist. Caddy returns 502 for `/mem/*` and the web root until they do. | A must not block on B, and B must not edit A's compose file. | A | done |
| D25 | **The db init script is `.sql`, not `.sh`.** | The `.sh` passed the entrypoint's `-x` check but failed from the bind mount with "bad interpreter". Postgres exited, restarted, skipped init, and `cognee` and `n8n-local` were never created, with no error surfaced by `tasks.py up`. The entrypoint pipes `.sql` through psql, so nothing needs an exec bit, which WSL2 (the demo laptop) preserves no better. | A | done |
| D26 | **Caddy's CORS allowlist takes one `header Origin` value per line.** | Two values on one line is invalid Caddyfile, and compose always sets `PUBLIC_URL`, so Caddy never started. The app is served same-origin through Caddy, so CORS only matters for a dev server on another port. | A | done |
| D27 | **`tasks.py generate` passes `--out` and `--force` through.** | Without them it could never regenerate over existing data. | A | done |
| D30 | **Cassette normalisation keeps an allowlist of headers (`content-type` only), not a denylist.** | The frozen format lists what to drop. Listing drops means a header nobody anticipated (a user agent, a new trace header) silently changes the request key and the cassette stops matching, which is only discovered when a paid recording turns out to be unusable. `accept` is excluded for the same reason: n8n, curl and the test client all send different ones. | A | done |
| D31 | **Twilio media bytes are not recorded.** Cassettes cover Sarvam calls and the Twilio Messages API. | A media URL carries SIDs generated by Twilio at record time and by the fakes at replay time, so the key could never match. The fakes already synthesise media deterministically (2F.6); what is worth paying for is what cannot be synthesised, which is all Sarvam. | A | done |
| D32 | **Recording requires `--live` and `HISAAB_LIVE=1`,** refused by `tasks.py` and again by the fakes at startup. Cassettes are bind-mounted out of the container. | Recording against the fakes would spend the window's budget and write cassettes of our own answers. Without the mount, recordings made in a live window would die with the container. | A | done |
| D33 | **`tasks.py snapshot` and `tasks.py reset` restore the demo database from a `pg_dump`.** Take the snapshot straight after `replay`, before any workflow run. | The ledger refuses UPDATE, DELETE and TRUNCATE, so there is no way back in place. A CP1 run that labels the demo credits cannot be undone, and WF10 skips credits that already carry a machine label: after one interrupted run, 67 of the window's 68 credits were labelled and CP1 could never again select three questions on that database. Restoring a dump is the only route back, so it became the blocker rather than a convenience. | A | done |
