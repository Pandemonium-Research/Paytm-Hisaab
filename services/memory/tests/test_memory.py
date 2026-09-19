from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient

from app.backends import HostedBackend, StubBackend, create_backend, dataset_name
from app.main import app


client = TestClient(app)


def remember(
    merchant_id: str,
    text: str,
    *,
    kind: str = "payer_fact",
    facts: Any | None = None,
    session_id: str | None = None,
) -> None:
    response = client.post(
        "/remember",
        json={
            "merchant_id": merchant_id,
            "kind": kind,
            "text": text,
            "facts": facts,
            "session_id": session_id,
        },
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True, "degraded": False}


def recall(
    merchant_id: str,
    query: str,
    *,
    top_k: int = 10,
    session_id: str | None = None,
) -> dict[str, Any]:
    response = client.post(
        "/recall",
        json={
            "merchant_id": merchant_id,
            "query": query,
            "session_id": session_id,
            "top_k": top_k,
        },
    )
    assert response.status_code == 200
    return response.json()


def test_health_reports_backend_without_calling_it() -> None:
    class ExplodingBackend:
        name = "exploding"

        def __getattr__(self, _name: str) -> Any:
            raise AssertionError("health touched the backend")

    app.state.backend = ExplodingBackend()
    assert client.get("/health").json() == {
        "ok": True,
        "backend": "exploding",
        "degraded": False,
    }
    assert client.get("/healthz").status_code == 200


def test_remember_and_recall_match_kind_text_and_facts_case_insensitively() -> None:
    remember(
        "merchant-a",
        "Ravi is the owner's brother",
        facts={"preferred_language": "Kannada"},
    )

    assert recall("merchant-a", "RAVI")["items"][0]["text"].startswith("Ravi")
    assert recall("merchant-a", "PAYER_FACT")["items"][0]["kind"] == "payer_fact"
    assert recall("merchant-a", "kannada")["items"][0]["facts"] == {
        "preferred_language": "Kannada"
    }


def test_recall_is_newest_first_and_honours_top_k() -> None:
    remember("merchant-a", "sale from Anu, first")
    remember("merchant-a", "sale from Bina, second")
    remember("merchant-a", "sale from Chitra, third")

    result = recall("merchant-a", "sale", top_k=2)

    assert result["degraded"] is False
    assert [item["text"] for item in result["items"]] == [
        "sale from Chitra, third",
        "sale from Bina, second",
    ]


def test_merchants_are_isolated() -> None:
    remember("merchant-a", "Private fact for alpha")
    remember("merchant-b", "Private fact for beta")

    assert recall("merchant-a", "beta")["items"] == []
    assert recall("merchant-b", "alpha")["items"] == []
    assert dataset_name("merchant-a") != dataset_name("merchant-b")


def test_session_id_can_scope_stub_recall() -> None:
    remember("merchant-a", "same keyword in session one", session_id="one")
    remember("merchant-a", "same keyword in session two", session_id="two")

    result = recall("merchant-a", "keyword", session_id="one")

    assert [item["session_id"] for item in result["items"]] == ["one"]


def test_improve_succeeds_and_forget_clears_only_the_merchant() -> None:
    remember("merchant-a", "shared needle")
    remember("merchant-b", "shared needle")

    improved = client.post("/improve", json={"merchant_id": "merchant-a"})
    forgotten = client.post(
        "/forget",
        json={"merchant_id": "merchant-a", "everything": True},
    )

    assert improved.json() == {"ok": True, "degraded": False}
    assert forgotten.json() == {"ok": True, "degraded": False}
    assert recall("merchant-a", "needle")["items"] == []
    assert len(recall("merchant-b", "needle")["items"]) == 1


def test_remember_index_now_is_optional_and_runs_improve_when_requested() -> None:
    class IndexTrackingStub(StubBackend):
        def __init__(self) -> None:
            super().__init__()
            self.improved_merchants: list[str] = []

        async def improve(self, merchant_id: str) -> None:
            self.improved_merchants.append(merchant_id)

    backend = IndexTrackingStub()
    app.state.backend = backend

    without_index = client.post(
        "/remember",
        json={"merchant_id": "merchant-a", "kind": "fact", "text": "first"},
    )
    with_index = client.post(
        "/remember",
        json={
            "merchant_id": "merchant-a",
            "kind": "fact",
            "text": "second",
            "index_now": True,
        },
    )

    assert without_index.json() == {"ok": True, "degraded": False}
    assert with_index.json() == {"ok": True, "degraded": False}
    assert backend.improved_merchants == ["merchant-a"]


def test_hosted_backend_uses_verified_write_and_index_endpoints() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={"status": "PipelineRunCompleted"},
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app.state.backend = HostedBackend(
        base_url="https://cognee.invalid/",
        api_key="test-key",
        client=http_client,
    )

    response = client.post(
        "/remember",
        json={
            "merchant_id": "merchant-a",
            "kind": "payer_fact",
            "text": "Ravi is family",
            "facts": {"language": "Kannada"},
            "index_now": True,
        },
    )

    asyncio.run(http_client.aclose())
    assert response.json() == {"ok": True, "degraded": False}
    assert [request.url.path for request in requests] == [
        "/api/v1/add_text",
        "/api/v1/cognify",
    ]
    assert json.loads(requests[0].content) == {
        "textData": [
            'kind: payer_fact\ntext: Ravi is family\nfacts: {"language":"Kannada"}'
        ],
        "datasetName": "hisaab-merchant-a",
    }
    assert json.loads(requests[1].content) == {
        "datasets": ["hisaab-merchant-a"],
        "runInBackground": False,
    }
    assert set(requests[0].extensions["timeout"].values()) == {60.0}
    assert set(requests[1].extensions["timeout"].values()) == {180.0}
    assert all(request.headers["x-api-key"] == "test-key" for request in requests)


def test_hosted_search_flattens_dataset_results_in_order_and_caps_top_k() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json=[
                {
                    "dataset_name": "first",
                    "search_result": ["first answer", "second answer"],
                },
                {"dataset_name": "empty", "search_result": []},
                {
                    "dataset_name": "second",
                    "search_result": ["third answer", "capped answer"],
                },
            ],
            request=request,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    app.state.backend = HostedBackend(
        base_url="https://cognee.invalid",
        api_key="test-key",
        client=http_client,
    )

    response = client.post(
        "/recall",
        json={"merchant_id": "merchant-a", "query": "family", "top_k": 3},
    )

    asyncio.run(http_client.aclose())
    assert response.json() == {
        "items": ["first answer", "second answer", "third answer"],
        "degraded": False,
    }
    assert len(requests) == 1
    assert requests[0].url.path == "/api/v1/search"
    assert json.loads(requests[0].content) == {
        "query": "family",
        "datasets": ["hisaab-merchant-a"],
        "topK": 3,
    }
    assert set(requests[0].extensions["timeout"].values()) == {60.0}


class RaisingBackend(StubBackend):
    name = "raising"

    async def remember(self, request: Any) -> None:
        raise RuntimeError("provider failed with secret material")

    async def recall(self, request: Any) -> list[Any]:
        raise RuntimeError("provider failed with secret material")

    async def improve(self, merchant_id: str) -> None:
        raise RuntimeError("provider failed with secret material")

    async def forget(self, request: Any) -> None:
        raise RuntimeError("provider failed with secret material")


@pytest.mark.parametrize(
    ("path", "body", "expected"),
    [
        (
            "/remember",
            {"merchant_id": "m", "kind": "fact", "text": "value"},
            {"ok": False, "degraded": True},
        ),
        (
            "/recall",
            {"merchant_id": "m", "query": "value", "top_k": 3},
            {"items": [], "degraded": True},
        ),
        ("/improve", {"merchant_id": "m"}, {"ok": False, "degraded": True}),
        ("/forget", {"merchant_id": "m"}, {"ok": False, "degraded": True}),
    ],
)
def test_backend_failures_are_degraded_not_server_errors(
    path: str,
    body: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    app.state.backend = RaisingBackend()

    response = client.post(path, json=body)

    assert response.status_code == 200
    assert response.json() == expected
    assert "provider failed" not in response.text


def test_hosted_backend_refuses_to_start_without_live_flag() -> None:
    with pytest.raises(RuntimeError, match=r"HISAAB_LIVE=1") as error:
        create_backend(
            {
                "MEMORY_BACKEND": "hosted",
                "HISAAB_LIVE": "0",
                "COGNEE_API_BASE_URL": "https://example.invalid",
                "COGNEE_API_KEY": "must-not-appear",
            }
        )
    assert "must-not-appear" not in str(error.value)


def test_self_backend_falls_back_to_stub() -> None:
    assert isinstance(create_backend({"MEMORY_BACKEND": "self"}), StubBackend)


def test_validation_errors_also_carry_degraded() -> None:
    response = client.post(
        "/recall",
        json={"merchant_id": "m", "query": "x", "top_k": 0},
    )
    assert response.status_code == 422
    assert response.json()["degraded"] is False
