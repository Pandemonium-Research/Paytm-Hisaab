from __future__ import annotations

import base64
import hashlib
import hmac
import html
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse


router = APIRouter(prefix="/twilio", tags=["twilio"])


@dataclass(frozen=True)
class StoredMedia:
    account_sid: str
    message_sid: str
    media_sid: str
    filename: str
    content_type: str
    content: bytes
    sha256: str


_media: dict[tuple[str, str, str], StoredMedia] = {}
_outbox: list[dict[str, Any]] = []
_lock = Lock()


def _settings() -> tuple[str, str]:
    return (
        os.environ.get("TWILIO_ACCOUNT_SID", "ACfake"),
        os.environ.get("TWILIO_AUTH_TOKEN", "fake"),
    )


def _require_basic_auth(request: Request, account_sid: str) -> None:
    expected_sid, auth_token = _settings()
    authorised = False
    try:
        scheme, encoded = request.headers.get("authorization", "").split(" ", 1)
        username, password = base64.b64decode(encoded, validate=True).decode().split(":", 1)
        authorised = (
            scheme.lower() == "basic"
            and hmac.compare_digest(username, account_sid)
            and hmac.compare_digest(username, expected_sid)
            and hmac.compare_digest(password, auth_token)
        )
    except (ValueError, UnicodeDecodeError):
        pass
    if not authorised:
        raise HTTPException(
            status_code=401,
            detail="Authenticate with the fake account SID and auth token.",
            headers={"WWW-Authenticate": 'Basic realm="Twilio API"'},
        )


async def _form(request: Request) -> dict[str, str]:
    if request.headers.get("content-type", "").split(";", 1)[0] != (
        "application/x-www-form-urlencoded"
    ):
        raise HTTPException(status_code=415, detail="Twilio requests are form encoded.")
    pairs = urllib.parse.parse_qsl(
        (await request.body()).decode("utf-8"),
        keep_blank_values=True,
    )
    return dict(pairs)


def _signature(url: str, parameters: dict[str, str], auth_token: str) -> str:
    payload = url + "".join(f"{name}{parameters[name]}" for name in sorted(parameters))
    digest = hmac.new(auth_token.encode(), payload.encode(), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


def _callback_is_local(url: str) -> bool:
    parsed = urllib.parse.urlparse(url)
    allowed_hosts = {
        "127.0.0.1",
        "localhost",
        "::1",
        "n8n",
        "core",
        "fakes",
        "caddy",
    }
    configured = os.environ.get("FAKES_CALLBACK_HOSTS", "")
    allowed_hosts.update(host.strip() for host in configured.split(",") if host.strip())
    return parsed.scheme == "http" and parsed.hostname in allowed_hosts


def _post_status_callback(url: str, parameters: dict[str, str]) -> None:
    if not _callback_is_local(url):
        # A typo in fake credentials must not turn a local run into an external request.
        return
    _, auth_token = _settings()
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(parameters).encode("utf-8"),
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "X-Twilio-Signature": _signature(url, parameters, auth_token),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=5):
            pass
    except OSError:
        # Real Twilio retries. The fake keeps the original message visible for manual replay.
        pass


@router.post("/2010-04-01/Accounts/{account_sid}/Messages.json")
async def create_message(
    account_sid: str,
    request: Request,
    background_tasks: BackgroundTasks,
) -> JSONResponse:
    _require_basic_auth(request, account_sid)
    form = await _form(request)
    if not form.get("To") or not form.get("From"):
        raise HTTPException(status_code=400, detail="To and From are required.")

    canonical = "&".join(f"{key}={form[key]}" for key in sorted(form))
    sid = "SM" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    now = datetime.now(timezone.utc)
    timestamp = now.strftime("%a, %d %b %Y %H:%M:%S +0000")
    media_urls = [
        value
        for key, value in sorted(form.items())
        if key == "MediaUrl" or key.startswith("MediaUrl")
    ]
    resource: dict[str, Any] = {
        "account_sid": account_sid,
        "api_version": "2010-04-01",
        "body": form.get("Body", ""),
        "date_created": timestamp,
        "date_sent": None,
        "date_updated": timestamp,
        "direction": "outbound-api",
        "error_code": None,
        "error_message": None,
        "from": form["From"],
        "messaging_service_sid": None,
        "num_media": str(len(media_urls)),
        "num_segments": "1",
        "price": None,
        "price_unit": "USD",
        "sid": sid,
        "status": "queued",
        "subresource_uris": {
            "media": (
                f"/2010-04-01/Accounts/{account_sid}/Messages/{sid}/Media.json"
            )
        },
        "to": form["To"],
        "uri": f"/2010-04-01/Accounts/{account_sid}/Messages/{sid}.json",
    }
    with _lock:
        _outbox.insert(
            0,
            {
                **resource,
                "media_urls": media_urls,
                "recorded_at": now.isoformat(),
            },
        )

    if callback_url := form.get("StatusCallback"):
        callback_parameters = {
            "AccountSid": account_sid,
            "ApiVersion": "2010-04-01",
            "ErrorCode": "",
            "From": form["From"],
            "MessageSid": sid,
            "MessageStatus": "delivered",
            "SmsSid": sid,
            "SmsStatus": "delivered",
            "To": form["To"],
        }
        background_tasks.add_task(_post_status_callback, callback_url, callback_parameters)

    return JSONResponse(resource, status_code=201)


@router.post("/_local/media")
async def upload_media(request: Request) -> JSONResponse:
    account_sid, _ = _settings()
    _require_basic_auth(request, account_sid)
    content = await request.body()
    if not content:
        raise HTTPException(status_code=400, detail="Media must not be empty.")
    if len(content) > 16 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Media exceeds the 16 MB webhook limit.")

    digest = hashlib.sha256(content).hexdigest()
    message_sid = "SM" + digest[:32]
    media_sid = "ME" + digest[32:64]
    item = StoredMedia(
        account_sid=account_sid,
        message_sid=message_sid,
        media_sid=media_sid,
        filename=request.headers.get("x-filename", "media"),
        content_type=request.headers.get("content-type", "application/octet-stream"),
        content=content,
        sha256=digest,
    )
    with _lock:
        _media[(account_sid, message_sid, media_sid)] = item
    path = (
        f"/twilio/2010-04-01/Accounts/{account_sid}/Messages/"
        f"{message_sid}/Media/{media_sid}"
    )
    return JSONResponse(
        {
            "account_sid": account_sid,
            "message_sid": message_sid,
            "sid": media_sid,
            "path": path,
            "content_type": item.content_type,
            "sha256": digest,
        },
        status_code=201,
    )


@router.get(
    "/2010-04-01/Accounts/{account_sid}/Messages/{message_sid}/Media/{media_sid}"
)
async def fetch_media(
    account_sid: str,
    message_sid: str,
    media_sid: str,
    request: Request,
) -> Response:
    _require_basic_auth(request, account_sid)
    with _lock:
        item = _media.get((account_sid, message_sid, media_sid))
    if item is None:
        raise HTTPException(status_code=404, detail="Media not found.")
    return Response(
        item.content,
        media_type=item.content_type,
        headers={
            "Content-Disposition": f'inline; filename="{item.filename}"',
            "X-Content-SHA256": item.sha256,
        },
    )


@router.get("/outbox", response_class=HTMLResponse)
async def outbox() -> HTMLResponse:
    with _lock:
        messages = list(_outbox)
    cards = []
    for message in messages:
        media = "".join(
            f"<li><code>{html.escape(url)}</code></li>" for url in message["media_urls"]
        )
        cards.append(
            "<article>"
            f"<h2>{html.escape(message['to'])}</h2>"
            f"<p class=timestamp>{html.escape(message['recorded_at'])}</p>"
            f"<p class=body>{html.escape(message['body']) or '<em>No text body</em>'}</p>"
            f"<h3>Media</h3><ul>{media or '<li>None</li>'}</ul>"
            f"<p><small>{html.escape(message['sid'])}</small></p>"
            "</article>"
        )
    body = "".join(cards) or "<p>No messages have been sent.</p>"
    document = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Hisaab fake WhatsApp outbox</title>
  <style>
    body {{ font: 16px/1.45 system-ui, sans-serif; margin: 2rem auto; max-width: 48rem;
            padding: 0 1rem; color: #17212b; background: #f4f7f9; }}
    article {{ background: white; border: 1px solid #d9e1e7; border-radius: .5rem;
               margin: 1rem 0; padding: 1rem 1.25rem; }}
    h1, h2, h3 {{ margin: 0 0 .5rem; }} h2 {{ font-size: 1.1rem; }}
    h3 {{ font-size: .9rem; margin-top: 1rem; }}
    .timestamp, small {{ color: #586875; }} .body {{ white-space: pre-wrap; }}
    code {{ overflow-wrap: anywhere; }}
  </style>
</head>
<body><h1>Fake WhatsApp outbox</h1><p>Newest first.</p>{body}</body>
</html>"""
    return HTMLResponse(document)


def reset_state() -> None:
    with _lock:
        _media.clear()
        _outbox.clear()
