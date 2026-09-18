from __future__ import annotations

import base64
import hashlib
import socket
import urllib.parse

import pytest
from fastapi import FastAPI, HTTPException, Request
from fastapi.testclient import TestClient

import tasks
from app.main import app
from app import twilio


client = TestClient(app)
AUTH = ("ACfake", "fake")


@pytest.fixture(autouse=True)
def fake_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TWILIO_ACCOUNT_SID", "ACfake")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "fake")
    twilio.reset_state()


def test_twilio_published_signature_vector() -> None:
    # Twilio's security guide uses this exact URL, form and token.
    url = "https://example.com/myapp.php?foo=1&bar=2"
    parameters = {
        "CallSid": "CA1234567890ABCDE",
        "Caller": "+14158675310",
        "Digits": "1234",
        "From": "+14158675310",
        "To": "+18005551212",
    }
    assert tasks.twilio_signature(url, parameters, "12345") == (
        "L/OH5YylLD5NRKLltdqwSvS0BnU="
    )


def test_signed_fake_wa_form_is_accepted_and_tampering_is_rejected() -> None:
    receiver = FastAPI()
    url = "http://testserver/inbound"

    @receiver.post("/inbound")
    async def inbound(request: Request) -> dict[str, bool]:
        parameters = dict(
            urllib.parse.parse_qsl((await request.body()).decode(), keep_blank_values=True)
        )
        if not tasks.verify_twilio_signature(
            url,
            parameters,
            request.headers.get("x-twilio-signature", ""),
            "fake",
        ):
            raise HTTPException(status_code=403, detail="bad Twilio signature")
        return {"accepted": True}

    receiver_client = TestClient(receiver)
    parameters = tasks._fake_wa_parameters("test", {"TWILIO_AUTH_TOKEN": "fake"})
    signature = tasks.twilio_signature(url, parameters, "fake")
    accepted = receiver_client.post(
        "/inbound",
        data=parameters,
        headers={"X-Twilio-Signature": signature},
    )
    tampered = receiver_client.post(
        "/inbound",
        data={**parameters, "Body": "changed"},
        headers={"X-Twilio-Signature": signature},
    )
    assert accepted.status_code == 200
    assert tampered.status_code == 403


def test_media_fetch_requires_auth_and_preserves_bytes_type_and_sha256() -> None:
    content = b"OggS\x00\x02fake-voice-note"
    uploaded = client.post(
        "/twilio/_local/media",
        content=content,
        auth=AUTH,
        headers={"Content-Type": "audio/ogg", "X-Filename": "note.ogg"},
    )
    assert uploaded.status_code == 201
    descriptor = uploaded.json()

    unauthorised = client.get(descriptor["path"])
    fetched = client.get(descriptor["path"], auth=AUTH)
    digest = hashlib.sha256(content).hexdigest()
    assert unauthorised.status_code == 401
    assert fetched.status_code == 200
    assert fetched.content == content
    assert fetched.headers["content-type"] == "audio/ogg"
    assert fetched.headers["x-content-sha256"] == digest == descriptor["sha256"]


def test_messages_api_populates_newest_first_outbox_and_calls_status_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    callbacks: list[tuple[str, dict[str, str]]] = []
    monkeypatch.setattr(
        twilio,
        "_post_status_callback",
        lambda url, parameters: callbacks.append((url, parameters)),
    )
    first = client.post(
        "/twilio/2010-04-01/Accounts/ACfake/Messages.json",
        auth=AUTH,
        data={
            "From": "whatsapp:+14155238886",
            "To": "whatsapp:+910000000001",
            "Body": "First",
            "StatusCallback": "http://n8n:5678/webhook/status",
        },
    )
    second = client.post(
        "/twilio/2010-04-01/Accounts/ACfake/Messages.json",
        auth=AUTH,
        data={
            "From": "whatsapp:+14155238886",
            "To": "whatsapp:+910000000002",
            "Body": "Second",
            "MediaUrl0": "http://fakes:8200/example.ogg",
        },
    )
    page = client.get("/twilio/outbox")

    assert first.status_code == second.status_code == 201
    assert first.json()["status"] == "queued"
    assert callbacks[0][0] == "http://n8n:5678/webhook/status"
    assert callbacks[0][1]["MessageStatus"] == "delivered"
    assert page.status_code == 200
    assert page.text.index("Second") < page.text.index("First")
    assert "whatsapp:+910000000002" in page.text
    assert "http://fakes:8200/example.ogg" in page.text


def test_non_local_callback_and_socket_are_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    called = False

    def should_not_open(*_args: object, **_kwargs: object) -> None:
        nonlocal called
        called = True

    monkeypatch.setattr(twilio.urllib.request, "urlopen", should_not_open)
    twilio._post_status_callback("https://api.twilio.com/status", {"MessageSid": "SM1"})
    assert called is False

    with pytest.raises(AssertionError, match="non-local socket"):
        socket.socket().connect(("203.0.113.1", 443))
