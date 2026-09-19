"""Assistant conversation persistence and merchant chat read model."""

import json
import urllib.error
from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.routers import assistant
from test_payments_postgres import NOW, api, read, request


pytestmark = pytest.mark.postgres


def inbound_body(merchant_id, *, message_id=None, text="Hello assistant", sim_at=NOW):
    return {"merchant_id": merchant_id, "message_id": message_id or f"M-{uuid4().hex}",
        "content_type": "text", "text": text, "language": "kn-IN", "sim_at": sim_at}


def outbound_body(merchant_id, conversation_id, *, text="Reply", sim_at=NOW, in_reply_to=None):
    return {"merchant_id": merchant_id, "conversation_id": conversation_id, "text": text,
        "language": "kn-IN", "in_reply_to": in_reply_to, "sim_at": sim_at}


def test_inbound_message_is_stored_and_readable(api):
    client, connection, profile = api
    body = inbound_body(profile["merchant_id"], text="Need help with my case")
    assert request(client, "/assistant/inbound", body, "app").status_code == 200
    items = read(client, "/app/conversation", profile["merchant_id"]).json()["items"]
    assert len(items) == 1
    assert items[0]["direction"] == "in"
    assert items[0]["message_id"] == body["message_id"]
    assert items[0]["text"] == body["text"]
    assert items[0]["content_type"] == "text"
    assert items[0]["language"] == "kn-IN"


def test_inbound_and_outbound_thread_oldest_first(api, monkeypatch):
    monkeypatch.setattr(assistant, "forward", lambda body: None)
    client, connection, profile = api
    first = inbound_body(profile["merchant_id"], message_id="M-first", text="First")
    second = inbound_body(profile["merchant_id"], message_id="M-second", text="Second")
    request(client, "/assistant/inbound", first, "app")
    conversation_id = f"wf31-{profile['merchant_id']}"
    request(client, "/assistant/outbound", outbound_body(profile["merchant_id"], conversation_id,
        text="Between", in_reply_to="M-first"), "conversation")
    request(client, "/assistant/inbound", second, "app")
    request(client, "/assistant/outbound", outbound_body(profile["merchant_id"], conversation_id,
        text="Last", in_reply_to="M-second"), "conversation")
    items = read(client, "/app/conversation", profile["merchant_id"]).json()["items"]
    assert [item["direction"] for item in items] == ["in", "out", "in", "out"]
    assert [item["text"] for item in items] == ["First", "Between", "Second", "Last"]


def test_another_merchants_conversation_is_not_returned(api, monkeypatch):
    monkeypatch.setattr(assistant, "forward", lambda body: None)
    client, connection, profile = api
    other = {**profile, "merchant_id": f"test-{uuid4().hex}"}
    connection.execute(text("INSERT INTO rails.merchants (merchant_id, profile) VALUES (:merchant, CAST(:profile AS jsonb))"),
        {"merchant": other["merchant_id"], "profile": json.dumps({**profile, "merchant_id": other["merchant_id"]})})
    request(client, "/assistant/inbound", inbound_body(profile["merchant_id"], text="Mine"), "app")
    request(client, "/assistant/inbound", inbound_body(other["merchant_id"], text="Theirs"), "app")
    assert read(client, "/app/conversation", profile["merchant_id"]).json()["items"][0]["text"] == "Mine"
    assert read(client, "/app/conversation", other["merchant_id"]).json()["items"][0]["text"] == "Theirs"


def test_future_sim_at_messages_are_hidden_when_clock_rewinds(api, monkeypatch):
    monkeypatch.setattr(assistant, "forward", lambda body: None)
    client, connection, profile = api
    future = (datetime.fromisoformat(NOW) + timedelta(days=1)).isoformat()
    client.post("/sim/clock", headers={"X-Hisaab-Key": "dev-admin"}, json={"sim_at": future}).raise_for_status()
    request(client, "/assistant/inbound", inbound_body(profile["merchant_id"], text="Future", sim_at=future), "app")
    assert len(read(client, "/app/conversation", profile["merchant_id"]).json()["items"]) == 1
    client.post("/sim/clock", headers={"X-Hisaab-Key": "dev-admin"}, json={"sim_at": NOW}).raise_for_status()
    assert read(client, "/app/conversation", profile["merchant_id"]).json()["items"] == []


def test_unknown_merchant_returns_404(api):
    client, connection, profile = api
    missing = f"test-{uuid4().hex}"
    assert read(client, "/app/conversation", missing).status_code == 404


def test_empty_conversation_returns_empty_items(api):
    client, connection, profile = api
    assert read(client, "/app/conversation", profile["merchant_id"]).json() == {"items": []}
