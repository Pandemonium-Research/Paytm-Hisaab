# Cassettes

Recorded provider responses. Everything here is written during a live window (plan §16a) and
committed, so each real call is paid for once and reused for the rest of the build.

This folder is **B's** (LANES.md): A owns the machinery, B records into it during L1.

## Recording, in a live window only

```bash
python tasks.py --live --record up      # needs .env.live with HISAAB_LIVE=1
```

Then run the spike or workflow as normal. Every request through the fakes goes to the real
provider, the response is saved here, and the caller gets the real answer. Commit what appears.

Both switches are required. `--record` without `--live`, or `HISAAB_RECORD=1` with
`HISAAB_LIVE=0`, is refused by `tasks.py` and again by the fakes at startup: recording the
fakes' own answers would spend the window's budget and leave worthless files.

Set `HISAAB_LIVE_WINDOW` (default `L1`) so each cassette records which window paid for it.

## Replaying

The default. `python tasks.py up` replays an exact match and otherwise falls back to the
deterministic rules, so an unrecorded request still gets a sensible answer.

## Layout and format

```
cassettes/<provider>/<request_key>.json
```

`request_key` is the SHA-256 of the canonical normalised request. The format is frozen in
`services/core/app/schemas/cassette.py`; `services/fakes/tests/data/golden-cassette.json` is a
committed example that core's test suite validates against that model.

Normalisation keeps only what can change a provider's answer: the method, path, query and body,
plus `content-type`. Authorisation, cookies, trace and request IDs, user agents, multipart
boundaries and cache-busting parameters are dropped, so the same logical call recorded through
n8n replays for core, curl or the tests. **No credential is ever written to a cassette**, which
is a test, not a promise.

## What is not recorded

Twilio media bytes. A media URL carries SIDs that Twilio generates when recording and the fakes
generate when replaying, so such a cassette could never match. The fakes already synthesise media
deterministically (2F.6). What is worth paying for, and is recorded, is what cannot be
synthesised: real Kannada speech, Bulbul audio, translations and Vision output.
