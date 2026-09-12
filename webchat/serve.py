"""Local web chat for hisaab-merchant, over Phinite's Chat API.

    python -m webchat.serve            # then open http://127.0.0.1:8090

Why a proxy rather than calling Phinite straight from the page: a browser page
cannot be given the workspace token (anyone with the page has your workspace), and
Phinite's Chat API is unlikely to send CORS headers for a file:// or localhost
origin. The proxy solves both - the token stays on this machine and the browser
only ever talks to 127.0.0.1.

Config, in .env or the environment:

    PHINITE_BASE            https://<phinite host>        (no trailing slash)
    PHINITE_TOKEN           workspace token, without "Bearer "
    PHINITE_INTEGRATION_ID  integration id from the Chat API deploy screen
    PHINITE_ENV             dev | staging | production
"""
import json
import os
import pathlib

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse

HERE = pathlib.Path(__file__).parent


def _env(name, default=""):
    # Tolerate a .env written with CRLF, which strips as an invisible \r otherwise.
    return (os.getenv(name, default) or "").strip().strip('"')


BASE = _env("PHINITE_BASE").rstrip("/")
TOKEN = _env("PHINITE_TOKEN")
INTEGRATION_ID = _env("PHINITE_INTEGRATION_ID")
ENVIRONMENT = _env("PHINITE_ENV", "dev")
TIMEOUT = httpx.Timeout(180.0, connect=15.0)

app = FastAPI(title="Hisaab web chat")


def _headers():
    if not TOKEN:
        raise HTTPException(500, "PHINITE_TOKEN is not set")
    return {"Authorization": "Bearer " + TOKEN}


@app.get("/")
def index():
    return FileResponse(HERE / "index.html")


@app.get("/api/config")
def config():
    """What the page shows in its footer, so a misconfig is visible not mysterious."""
    return {
        "base": BASE or None,
        "integration_id": INTEGRATION_ID or None,
        "env": ENVIRONMENT,
        "token_set": bool(TOKEN),
        "ready": bool(BASE and TOKEN and INTEGRATION_ID),
    }


@app.post("/api/start")
async def start():
    if not (BASE and INTEGRATION_ID):
        raise HTTPException(500, "PHINITE_BASE and PHINITE_INTEGRATION_ID must be set")
    url = "%s/chat_api/%s/%s" % (BASE, INTEGRATION_ID, ENVIRONMENT)
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        try:
            r = await client.post(url, headers=_headers())
        except httpx.HTTPError as e:
            raise HTTPException(502, "cannot reach Phinite: %s" % e)
    if r.status_code != 200:
        raise HTTPException(r.status_code, r.text[:400])
    return r.json()


@app.post("/api/send/{session_id}")
async def send(session_id: str, request: Request):
    """Pass the NDJSON stream straight through, line by line.

    Streaming rather than buffering matters: the agent emits `processing` lines
    while tools run, and a merchant staring at a dead screen for ten seconds is a
    worse demo than one watching it think.
    """
    body = await request.json()
    url = "%s/chat_api/%s" % (BASE, session_id)

    async def relay():
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            try:
                async with client.stream(
                    "POST", url, headers=_headers(), json=body
                ) as r:
                    if r.status_code != 200:
                        text = (await r.aread()).decode("utf-8", "replace")[:400]
                        yield json.dumps(
                            {"error": "HTTP %s: %s" % (r.status_code, text)}
                        ) + "\n"
                        return
                    async for line in r.aiter_lines():
                        if line.strip():
                            yield line + "\n"
            except httpx.HTTPError as e:
                yield json.dumps({"error": "stream failed: %s" % e}) + "\n"

    return StreamingResponse(relay(), media_type="application/x-ndjson")


if __name__ == "__main__":
    import uvicorn

    missing = [
        n for n, v in (("PHINITE_BASE", BASE), ("PHINITE_TOKEN", TOKEN),
                       ("PHINITE_INTEGRATION_ID", INTEGRATION_ID)) if not v
    ]
    if missing:
        print("!! not configured: %s" % ", ".join(missing))
        print("   the page will load and tell you the same thing.\n")
    print("   http://127.0.0.1:8090   (env: %s)\n" % ENVIRONMENT)
    uvicorn.run(app, host="127.0.0.1", port=8090, log_level="warning")
