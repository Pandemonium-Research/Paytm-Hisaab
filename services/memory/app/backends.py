from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from collections.abc import Mapping
from typing import Any, Protocol

import httpx

from .models import ForgetRequest, RecallRequest, RememberRequest


logger = logging.getLogger(__name__)
TOKEN_RE = re.compile(r"[\w]+", re.UNICODE)


def dataset_name(merchant_id: str) -> str:
    """Return the sole Cognee dataset assigned to a merchant."""
    return f"hisaab-{merchant_id}"


def compose_entry(request: RememberRequest) -> str:
    """Make every caller-supplied memory field searchable by Cognee and the stub."""
    parts = [f"kind: {request.kind}", f"text: {request.text}"]
    if request.facts is not None:
        facts = json.dumps(
            request.facts,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        parts.append(f"facts: {facts}")
    return "\n".join(parts)


class MemoryBackend(Protocol):
    name: str

    async def remember(self, request: RememberRequest) -> None: ...

    async def recall(self, request: RecallRequest) -> list[Any]: ...

    async def improve(self, merchant_id: str) -> None: ...

    async def forget(self, request: ForgetRequest) -> None: ...


@dataclass(frozen=True)
class StoredMemory:
    kind: str
    text: str
    facts: Any | None
    session_id: str | None
    entry: str

    def public_item(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "text": self.text,
            "facts": self.facts,
            "session_id": self.session_id,
        }


class StubBackend:
    name = "stub"

    def __init__(self) -> None:
        self._memories: dict[str, list[StoredMemory]] = {}
        self._lock = asyncio.Lock()

    async def remember(self, request: RememberRequest) -> None:
        memory = StoredMemory(
            kind=request.kind,
            text=request.text,
            facts=request.facts,
            session_id=request.session_id,
            entry=compose_entry(request),
        )
        async with self._lock:
            self._memories.setdefault(dataset_name(request.merchant_id), []).append(memory)

    async def recall(self, request: RecallRequest) -> list[dict[str, Any]]:
        query = request.query.casefold()
        keywords = set(TOKEN_RE.findall(query))
        async with self._lock:
            candidates = list(self._memories.get(dataset_name(request.merchant_id), ()))

        matches: list[dict[str, Any]] = []
        for memory in reversed(candidates):
            if request.session_id is not None and memory.session_id != request.session_id:
                continue
            searchable = memory.entry.casefold()
            if query in searchable or any(keyword in searchable for keyword in keywords):
                matches.append(memory.public_item())
                if len(matches) == request.top_k:
                    break
        return matches

    async def improve(self, merchant_id: str) -> None:
        # The deterministic stub has no derived graph to improve.
        del merchant_id

    async def forget(self, request: ForgetRequest) -> None:
        # `everything` is intentionally scoped to this merchant's dataset.
        async with self._lock:
            self._memories.pop(dataset_name(request.merchant_id), None)


class HostedBackend:
    name = "hosted"

    # Tenant verification: POST /api/v1/remember/entry rejects valid entries with
    # HTTP 400, while POST /api/v1/recall never responds. Do not use either here.

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._client = client

    async def _post(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        timeout: float,
    ) -> Any:
        headers = {"X-Api-Key": self._api_key, "Content-Type": "application/json"}
        url = f"{self._base_url}{path}"
        if self._client is not None:
            response = await self._client.post(
                url,
                json=payload,
                headers=headers,
                timeout=timeout,
            )
        else:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    url,
                    json=payload,
                    headers=headers,
                    timeout=timeout,
                )
        response.raise_for_status()
        if not response.content:
            return None
        return response.json()

    async def remember(self, request: RememberRequest) -> None:
        payload = {
            "textData": [compose_entry(request)],
            "datasetName": dataset_name(request.merchant_id),
        }
        await self._post("/api/v1/add_text", payload, timeout=60.0)

    async def recall(self, request: RecallRequest) -> list[Any]:
        payload = {
            "query": request.query,
            "datasets": [dataset_name(request.merchant_id)],
            "topK": request.top_k,
        }
        result = await self._post("/api/v1/search", payload, timeout=60.0)
        return _recall_items(result, top_k=request.top_k)

    async def improve(self, merchant_id: str) -> None:
        await self._post(
            "/api/v1/cognify",
            {
                "datasets": [dataset_name(merchant_id)],
                "runInBackground": False,
            },
            timeout=180.0,
        )

    async def forget(self, request: ForgetRequest) -> None:
        payload = (
            {"everything": True}
            if request.everything
            else {"dataset": dataset_name(request.merchant_id)}
        )
        await self._post(
            "/api/v1/forget",
            payload,
            timeout=60.0,
        )


def _recall_items(result: Any, *, top_k: int) -> list[str]:
    """Flatten hosted search results across datasets, preserving their order."""
    if not isinstance(result, list):
        return []

    items: list[str] = []
    for dataset_result in result:
        if not isinstance(dataset_result, dict):
            continue
        search_result = dataset_result.get("search_result")
        if not isinstance(search_result, list):
            continue
        for item in search_result:
            if isinstance(item, str) and item:
                items.append(item)
                if len(items) == top_k:
                    return items
    return items


_self_warning_logged = False


def create_backend(environ: Mapping[str, str] | None = None) -> MemoryBackend:
    global _self_warning_logged

    env = os.environ if environ is None else environ
    selected = env.get("MEMORY_BACKEND", "stub").strip().lower()
    if selected == "stub":
        return StubBackend()
    if selected == "self":
        if not _self_warning_logged:
            logger.warning("MEMORY_BACKEND=self is not implemented; using the in-process stub")
            _self_warning_logged = True
        return StubBackend()
    if selected != "hosted":
        raise RuntimeError("MEMORY_BACKEND must be one of: hosted, self, stub")
    if env.get("HISAAB_LIVE") != "1":
        raise RuntimeError("MEMORY_BACKEND=hosted requires HISAAB_LIVE=1")

    base_url = env.get("COGNEE_API_BASE_URL", "").strip()
    api_key = env.get("COGNEE_API_KEY", "").strip()
    missing = [
        name
        for name, value in (
            ("COGNEE_API_BASE_URL", base_url),
            ("COGNEE_API_KEY", api_key),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"hosted memory requires {', '.join(missing)}")
    return HostedBackend(base_url=base_url, api_key=api_key)
