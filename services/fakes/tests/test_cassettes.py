"""Record and replay (task 2F.2).

The expensive failure is a cassette recorded in a paid window that never matches afterwards, so
most of these tests are about the request key being stable across everything that legitimately
varies between the recording run and every replay.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app import cassettes
from app.main import app


def norm(**overrides):
    base = dict(
        method="POST",
        path="/sarvam/v1/chat/completions",
        query={},
        headers={"content-type": "application/json"},
        body={"model": "sarvam-105b", "messages": [{"role": "user", "content": "hello"}]},
    )
    base.update(overrides)
    return cassettes.normalise(**base)


def test_volatile_transport_detail_does_not_change_the_key() -> None:
    baseline = cassettes.request_key(norm())
    varying = [
        {"headers": {"content-type": "application/json", "authorization": "Bearer real-key"}},
        {"headers": {"content-type": "application/json", "x-request-id": "req-123"}},
        {"headers": {"content-type": "application/json", "traceparent": "00-abc-def-01"}},
        {"headers": {"content-type": "application/json", "cookie": "session=1"}},
        {"headers": {"content-type": "application/json", "user-agent": "n8n/2.39.7"}},
        {"headers": {"content-type": "application/json", "idempotency-key": "k-1"}},
        # Varies by client, so it must not decide whether a paid recording is reusable.
        {"headers": {"content-type": "application/json", "accept": "*/*"}},
        {"headers": {"content-type": "application/json", "accept": "application/json"}},
        {"headers": {"content-type": "application/json; charset=utf-8"}},
        {"headers": {"Content-Type": "application/json"}},
        {"query": {"_": "1789720000"}},
        {"query": {"nonce": "abcdef"}},
    ]
    for overrides in varying:
        assert cassettes.request_key(norm(**overrides)) == baseline, overrides


def test_multipart_boundary_is_dropped() -> None:
    a = norm(headers={"content-type": "multipart/form-data; boundary=----abc123"})
    b = norm(headers={"content-type": "multipart/form-data; boundary=----zzz999"})
    assert cassettes.request_key(a) == cassettes.request_key(b)


def test_business_content_does_change_the_key() -> None:
    baseline = cassettes.request_key(norm())
    different = [
        {"body": {"model": "sarvam-105b", "messages": [{"role": "user", "content": "other"}]}},
        {"body": {"model": "sarvam-m", "messages": [{"role": "user", "content": "hello"}]}},
        {"path": "/sarvam/v1/speech-to-text"},
        {"method": "GET"},
        {"query": {"language": "kn"}},
    ]
    for overrides in different:
        assert cassettes.request_key(norm(**overrides)) != baseline, overrides


def test_key_ignores_json_key_order_but_not_array_order() -> None:
    a = norm(body={"model": "m", "messages": [{"role": "user", "content": "x"}]})
    b = norm(body={"messages": [{"content": "x", "role": "user"}], "model": "m"})
    assert cassettes.request_key(a) == cassettes.request_key(b)
    c = norm(body={"messages": [{"role": "user"}, {"role": "system"}]})
    d = norm(body={"messages": [{"role": "system"}, {"role": "user"}]})
    assert cassettes.request_key(c) != cassettes.request_key(d)


def test_twilio_account_sid_in_the_path_is_normalised() -> None:
    real = norm(path="/twilio/2010-04-01/Accounts/AC" + "b" * 32 + "/Messages.json")
    fake = norm(path="/twilio/2010-04-01/Accounts/AC" + "f" * 32 + "/Messages.json")
    assert cassettes.request_key(real) == cassettes.request_key(fake)


def test_saved_cassette_replays_before_the_rules(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(cassettes, "CASSETTE_ROOT", tmp_path)
    body = {"model": "sarvam-105b", "messages": [{"role": "user", "content": "recorded case"}]}
    normalised = cassettes.normalise(
        method="POST",
        path="/sarvam/v1/chat/completions",
        query={},
        headers={"content-type": "application/json"},
        body=body,
    )
    real_answer = {"choices": [{"message": {"role": "assistant", "content": "ನಮಸ್ಕಾರ"}}]}
    cassettes.save(
        provider="sarvam",
        endpoint="/sarvam/v1/chat/completions",
        normalised=normalised,
        status=200,
        headers={"content-type": "application/json"},
        body=real_answer,
        live_window="L1",
    )

    client = TestClient(app)
    replayed = client.post(
        "/sarvam/v1/chat/completions",
        json=body,
        headers={"Authorization": "Bearer fake"},
    )
    assert replayed.status_code == 200
    # The recorded Kannada text, not the fakes' deterministic English sentence.
    assert replayed.json() == real_answer

    missed = client.post(
        "/sarvam/v1/chat/completions",
        json={"model": "sarvam-105b", "messages": [{"role": "user", "content": "unrecorded"}]},
        headers={"Authorization": "Bearer fake"},
    )
    assert missed.status_code == 200
    assert missed.json()["choices"][0]["message"]["content"].startswith("Deterministic local")


def test_recording_needs_both_switches(monkeypatch) -> None:
    monkeypatch.setenv("HISAAB_RECORD", "1")
    monkeypatch.setenv("HISAAB_LIVE", "0")
    assert cassettes.recording() is False
    with pytest.raises(RuntimeError, match="HISAAB_LIVE=1"):
        cassettes.record_guard()

    monkeypatch.setenv("HISAAB_LIVE", "1")
    assert cassettes.recording() is True
    cassettes.record_guard()


def test_forward_refuses_outside_record_mode(monkeypatch) -> None:
    monkeypatch.delenv("HISAAB_RECORD", raising=False)
    monkeypatch.setenv("HISAAB_LIVE", "0")
    with pytest.raises(RuntimeError, match="outside record mode"):
        cassettes.forward(
            upstream="https://api.sarvam.ai",
            method="POST",
            path="/v1/chat/completions",
            query={},
            headers={},
            raw_body=b"{}",
        )


def test_saved_cassette_matches_the_frozen_format(tmp_path, monkeypatch) -> None:
    """The on-disk shape must satisfy core's ProviderCassette (task 1.3)."""
    monkeypatch.setattr(cassettes, "CASSETTE_ROOT", tmp_path)
    path = cassettes.save(
        provider="sarvam",
        endpoint="/sarvam/v1/chat/completions",
        normalised=norm(),
        status=200,
        headers={"content-type": "application/json"},
        body={"ok": True},
        live_window="L1",
    )
    written = json.loads(path.read_text())
    assert written["schema_version"] == 1
    assert set(written) == {
        "schema_version", "provider", "endpoint", "request_key",
        "normalised_request", "response", "live_window", "recorded_at",
    }
    assert set(written["normalised_request"]) == {"method", "path", "query", "headers", "body"}
    assert set(written["response"]) == {"status", "headers", "body"}
    assert len(written["request_key"]) == 64 and written["request_key"].islower()
    # tests/data/golden-cassette.json is the committed copy of this shape; core's contract
    # test validates it against ProviderCassette, which is what keeps the two services aligned.
    from pathlib import Path

    golden = json.loads(
        (Path(__file__).parent / "data/golden-cassette.json").read_text(encoding="utf-8")
    )
    assert set(golden) == set(written)
    assert set(golden["normalised_request"]) == set(written["normalised_request"])
    assert set(golden["response"]) == set(written["response"])


def test_credentials_never_reach_a_cassette() -> None:
    """Cassettes are committed to the repo, so a recorded key would be a leaked key."""
    normalised = cassettes.normalise(
        method="POST",
        path="/sarvam/v1/chat/completions",
        query={"api_key": "should-not-matter"},
        headers={
            "content-type": "application/json",
            "authorization": "Bearer sk-live-REAL-SECRET",
            "api-subscription-key": "REAL-SECRET",
            "cookie": "session=REAL",
        },
        body={"model": "sarvam-105b", "messages": []},
    )
    assert "REAL" not in json.dumps(normalised)
    assert normalised["headers"] == {"content-type": "application/json"}
