from __future__ import annotations

import hashlib
import json
import os
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse

from . import cassettes


router = APIRouter(prefix="/sarvam/v1", tags=["sarvam"])

PREDICTION_LABELS = frozenset(
    {
        "taxable_supply",
        "exempt_supply",
        "personal_transfer",
        "inter_account",
        "non_business",
        "refund_reversal",
        "duplicate",
        "unclassified",
    }
)
ANSWER_CHOICES = frozenset(
    {
        "sale",
        "family",
        "own_money",
        "loan_or_gift",
        "refund",
        "double_payment",
        "not_sure",
    }
)


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _request_text(body: dict[str, Any]) -> str:
    parts: list[str] = []
    for message in body.get("messages", []):
        content = message.get("content", "")
        if isinstance(content, str):
            parts.append(content)
        else:
            parts.append(_canonical(content))
    return " ".join(parts).lower()


def _rule_label(text: str) -> str:
    """Mirror the classify-rules precedence with the signals available in a prompt."""
    if '"channel":"upi_reversal"' in text or "upi reversal" in text:
        return "refund_reversal"
    if '"own_account_cue":true' in text or any(
        cue in text for cue in ("own account", "my account", "self transfer")
    ):
        return "inter_account"
    if '"merchant_has_paid_them":true' in text:
        return "refund_reversal"
    if any(cue in text for cue in ("double payment", "duplicate", "paid twice")):
        return "duplicate"
    if '"channel":"bank_transfer"' in text or any(
        cue in text for cue in ("loan", "gift", "chit", "insurance claim", "deposit")
    ):
        return "non_business"
    if '"surname_cue":true' in text or any(
        cue in text
        for cue in ("family", "wife", "husband", "sister", "brother", "mother", "father")
    ):
        return "personal_transfer"
    if any(cue in text for cue in ("vegetable", "fruit", "exempt")):
        return "exempt_supply"
    if '"has_bill":true' in text or any(cue in text for cue in ("sale", "bill", "customer")):
        return "taxable_supply"
    return "unclassified"


def _answer_for(label: str) -> str:
    return {
        "taxable_supply": "sale",
        "exempt_supply": "sale",
        "personal_transfer": "family",
        "inter_account": "own_money",
        "non_business": "loan_or_gift",
        "refund_reversal": "refund",
        "duplicate": "double_payment",
        "unclassified": "not_sure",
    }[label]


def _enum_value(values: list[Any], name: str, label: str) -> Any:
    if name.lower() == "label" and label in values:
        return label
    answer = _answer_for(label)
    if name.lower() == "answer" and answer in values:
        return answer
    if "unclassified" in values:
        return label if label in values else "unclassified"
    if "not_sure" in values:
        return answer if answer in values else "not_sure"
    return values[0]


def _schema_value(
    schema: dict[str, Any],
    *,
    name: str,
    label: str,
    root: dict[str, Any],
) -> Any:
    if "$ref" in schema:
        target: Any = root
        for component in schema["$ref"].removeprefix("#/").split("/"):
            target = target[component.replace("~1", "/").replace("~0", "~")]
        return _schema_value(target, name=name, label=label, root=root)
    if "const" in schema:
        return schema["const"]
    if values := schema.get("enum"):
        return _enum_value(values, name, label)
    for union_name in ("oneOf", "anyOf"):
        if alternatives := schema.get(union_name):
            chosen = next(
                (
                    option
                    for option in alternatives
                    if option.get("type") != "null" and option.get("const") is not None
                ),
                next(
                    (option for option in alternatives if option.get("type") != "null"),
                    alternatives[0],
                ),
            )
            return _schema_value(chosen, name=name, label=label, root=root)
    if parts := schema.get("allOf"):
        return _schema_value(parts[0], name=name, label=label, root=root)

    value_type = schema.get("type")
    if isinstance(value_type, list):
        value_type = next((item for item in value_type if item != "null"), "null")
    if value_type == "object" or "properties" in schema:
        properties = schema.get("properties", {})
        required = schema.get("required", list(properties))
        return {
            key: _schema_value(value, name=key, label=label, root=root)
            for key, value in properties.items()
            if key in required
        }
    if value_type == "array":
        length = max(1, schema.get("minItems", 0))
        if not schema.get("minItems"):
            length = 0
        return [
            _schema_value(schema.get("items", {}), name=name, label=label, root=root)
            for _ in range(length)
        ]
    if value_type in {"number", "integer"}:
        if name == "confidence":
            return 0.65
        return max(schema.get("minimum", 0), 0)
    if value_type == "boolean":
        return False
    if value_type == "null":
        return None

    lowered = name.lower()
    if lowered == "label":
        return label
    if lowered == "answer":
        return _answer_for(label)
    if lowered == "intent":
        return "answer_question"
    if lowered == "language":
        return "en"
    if lowered == "reason_en":
        return "The deterministic fake applied the local classification rules."
    if lowered in {"reason", "text", "summary"}:
        return "Generated locally by the deterministic Sarvam fake."
    if schema.get("format") == "date":
        return "2026-03-24"
    return schema.get("default", "fake")


def _structured_content(body: dict[str, Any], label: str) -> str | None:
    response_format = body.get("response_format")
    if not isinstance(response_format, dict):
        return None
    if response_format.get("type") == "json_object":
        return _canonical({"label": label, "answer": _answer_for(label)})
    if response_format.get("type") != "json_schema":
        return None
    wrapper = response_format.get("json_schema", {})
    schema = wrapper.get("schema", wrapper)
    if not isinstance(schema, dict):
        raise HTTPException(status_code=400, detail="response_format has no JSON schema")
    return _canonical(_schema_value(schema, name="response", label=label, root=schema))


def _selected_tool(body: dict[str, Any]) -> dict[str, Any] | None:
    tools = body.get("tools")
    if not isinstance(tools, list) or not tools:
        return None
    if body.get("tool_choice") == "none":
        return None
    if body.get("messages", [{}])[-1].get("role") == "tool":
        return None
    choice = body.get("tool_choice")
    if isinstance(choice, dict):
        wanted = choice.get("function", {}).get("name")
        return next(
            (tool for tool in tools if tool.get("function", {}).get("name") == wanted),
            tools[0],
        )
    return tools[0]


SARVAM_UPSTREAM = "https://api.sarvam.ai"


def _normalised(request: Request, body: Any) -> dict[str, Any]:
    return cassettes.normalise(
        method=request.method,
        path=request.url.path,
        query=dict(request.query_params),
        headers=dict(request.headers),
        body=body,
    )


@router.post("/chat/completions")
async def chat_completions(
    request: Request,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    expected_key = os.environ.get("SARVAM_API_KEY", "fake")
    if authorization != f"Bearer {expected_key}":
        return JSONResponse(
            {
                "error": {
                    "message": "Use the fake Sarvam API key.",
                    "type": "invalid_request_error",
                    "param": None,
                    "code": "invalid_api_key",
                }
            },
            status_code=401,
        )
    try:
        body = await request.json()
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Request body must be JSON.") from exc
    if not isinstance(body, dict) or not isinstance(body.get("messages"), list):
        raise HTTPException(status_code=400, detail="messages must be an array.")

    normalised = _normalised(request, body)
    request_key = cassettes.request_key(normalised)

    if cassettes.recording():
        # A live window: pay for the real answer once, keep it, and hand it straight back.
        status, headers, raw = cassettes.forward(
            upstream=SARVAM_UPSTREAM,
            method="POST",
            path=request.url.path.removeprefix("/sarvam"),
            query=dict(request.query_params),
            headers={"content-type": "application/json", "authorization": authorization or ""},
            raw_body=json.dumps(body).encode("utf-8"),
        )
        recorded = json.loads(raw) if raw else None
        cassettes.save(
            provider="sarvam",
            endpoint=request.url.path,
            normalised=normalised,
            status=status,
            headers=headers,
            body=recorded,
            live_window=cassettes.live_window(),
        )
        return JSONResponse(recorded, status_code=status)

    if replay := cassettes.replay("sarvam", normalised):
        return JSONResponse(replay.get("body"), status_code=replay.get("status", 200))

    text = _request_text(body)
    label = _rule_label(text)
    message: dict[str, Any] = {"role": "assistant"}
    finish_reason = "stop"
    if tool := _selected_tool(body):
        function = tool.get("function", {})
        parameters = function.get("parameters", {"type": "object", "properties": {}})
        arguments = _schema_value(
            parameters,
            name="arguments",
            label=label,
            root=parameters,
        )
        message.update(
            {
                "content": None,
                "refusal": None,
                "tool_calls": [
                    {
                        "id": "call_" + request_key[:24],
                        "type": "function",
                        "function": {
                            "name": function.get("name", "tool"),
                            "arguments": _canonical(arguments),
                        },
                    }
                ],
            }
        )
        finish_reason = "tool_calls"
    else:
        content = _structured_content(body, label)
        if content is None:
            content = f"Deterministic local response: {label}."
        message.update({"content": content, "refusal": None})

    prompt_tokens = max(1, len(_canonical(body)) // 4)
    completion_tokens = max(1, len(_canonical(message)) // 4)
    response = {
        "id": "chatcmpl-" + request_key[:32],
        "object": "chat.completion",
        "created": 0,
        "model": body.get("model", "sarvam-105b"),
        "choices": [
            {
                "index": 0,
                "message": message,
                "logprobs": None,
                "finish_reason": finish_reason,
            }
        ],
        "usage": {
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": prompt_tokens + completion_tokens,
        },
        "system_fingerprint": "fake-" + request_key[:12],
    }
    return JSONResponse(response)
