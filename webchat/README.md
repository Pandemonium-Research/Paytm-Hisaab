# Local web chat

Phinite has no embeddable Web Chat widget — the channel list is Voice, Chat (an AI
*provider* integration, not a user channel), Jira, Email, Teams, Slack, Twilio,
WhatsApp and Chat API. WhatsApp needs BSP approval we decided against, so the merchant
conversation runs against **Chat API** with this page in front of it.

```bash
python -m webchat.serve      # http://127.0.0.1:8090
```

Four variables, in `.env`: `PHINITE_BASE`, `PHINITE_TOKEN`, `PHINITE_INTEGRATION_ID`,
`PHINITE_ENV`. The page tells you which are missing rather than failing silently.

## Why a proxy and not a plain HTML file

Two reasons, both of which bite immediately otherwise:

- The workspace token cannot go in the browser. Anyone with the page would hold the
  workspace.
- Phinite's Chat API almost certainly sends no CORS headers for a `file://` or
  localhost origin, so a page calling it directly is blocked with nothing useful in
  the console.

The proxy keeps the token on the machine and the browser only talks to 127.0.0.1.

It also cannot be a published Artifact: those run under a CSP that blocks `fetch` to
any non-allowlisted host.

## What the page does

- `POST /chat_api/{integration_id}/{env}` on load, renders the greeting, keeps the
  `session_id`
- `POST /chat_api/{session_id}` per turn, reading the NDJSON stream line by line so
  `processing` lines appear while tools run rather than after
- Renders the agent's pipe-separated answer list as tap targets, which is the point of
  the attestation loop — the merchant taps, she does not type
- Kannada throughout (Noto Sans Kannada), phone-shaped, one question on screen at a time
