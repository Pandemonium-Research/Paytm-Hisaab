from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.sarvam import ANSWER_CHOICES, PREDICTION_LABELS


client = TestClient(app)
HEADERS = {"Authorization": "Bearer fake"}


@pytest.fixture(autouse=True)
def fake_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SARVAM_API_KEY", "fake")


def test_same_chat_request_has_byte_identical_response() -> None:
    body = {
        "model": "sarvam-105b",
        "messages": [
            {
                "role": "user",
                "content": "Classify a customer sale with an itemised bill.",
            }
        ],
        "temperature": 0,
    }
    first = client.post("/sarvam/v1/chat/completions", headers=HEADERS, json=body)
    second = client.post("/sarvam/v1/chat/completions", headers=HEADERS, json=body)
    assert first.status_code == second.status_code == 200
    assert first.content == second.content


def test_tool_call_is_openai_shaped_and_arguments_parse() -> None:
    body = {
        "model": "sarvam-105b",
        "messages": [{"role": "user", "content": "This came from my own account."}],
        "tools": [
            {
                "type": "function",
                "function": {
                    "name": "record_label",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string", "enum": sorted(PREDICTION_LABELS)},
                            "answer": {"type": "string", "enum": sorted(ANSWER_CHOICES)},
                        },
                        "required": ["label", "answer"],
                        "additionalProperties": False,
                    },
                },
            }
        ],
    }
    response = client.post("/sarvam/v1/chat/completions", headers=HEADERS, json=body)
    choice = response.json()["choices"][0]
    call = choice["message"]["tool_calls"][0]
    arguments = json.loads(call["function"]["arguments"])
    assert response.status_code == 200
    assert choice["finish_reason"] == "tool_calls"
    assert call["type"] == "function"
    assert arguments == {"answer": "own_money", "label": "inter_account"}


def test_json_schema_response_is_parseable_and_uses_fixed_vocabularies() -> None:
    schema = {
        "type": "object",
        "properties": {
            "label": {"type": "string", "enum": sorted(PREDICTION_LABELS)},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "answer": {"type": "string", "enum": sorted(ANSWER_CHOICES)},
            "reason_en": {"type": "string"},
        },
        "required": ["label", "confidence", "answer", "reason_en"],
        "additionalProperties": False,
    }
    body = {
        "model": "sarvam-105b",
        "messages": [{"role": "user", "content": "My sister sent family money."}],
        "response_format": {
            "type": "json_schema",
            "json_schema": {"name": "classification", "strict": True, "schema": schema},
        },
    }
    response = client.post("/sarvam/v1/chat/completions", headers=HEADERS, json=body)
    parsed = json.loads(response.json()["choices"][0]["message"]["content"])
    assert response.status_code == 200
    assert parsed["label"] == "personal_transfer"
    assert parsed["answer"] == "family"
    assert parsed["label"] in PREDICTION_LABELS
    assert parsed["answer"] in ANSWER_CHOICES


def test_chat_requires_fake_bearer_key() -> None:
    response = client.post(
        "/sarvam/v1/chat/completions",
        json={"model": "sarvam-105b", "messages": []},
    )
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_api_key"
