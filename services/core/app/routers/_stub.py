"""Small route factory used only while Phase 2A responses are fixtures."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..auth import require_role
from ..fixtures import response_fixture
from ..schemas.ledger import EntryKind


def add_get(
    router: APIRouter,
    *,
    area: str,
    endpoint: str,
    path: str,
    response_model: type[BaseModel],
    query_model: type[BaseModel] | None = None,
) -> None:
    if query_model is None:
        async def stub(_: Any = Depends(require_role(endpoint))) -> dict[str, Any]:
            return response_fixture(area, endpoint, response_model)
    else:
        async def stub(query: Any, _: Any = Depends(require_role(endpoint))) -> dict[str, Any]:
            del query
            return response_fixture(area, endpoint, response_model)

        stub.__annotations__["query"] = Annotated[query_model, Query()]

    stub.__name__ = endpoint.lower().replace(" ", "_").replace("/", "_")
    router.add_api_route(path, stub, methods=["GET"], response_model=response_model)


def add_post(
    router: APIRouter,
    *,
    area: str,
    endpoint: str,
    path: str,
    request_model: type[BaseModel],
    response_model: type[BaseModel],
    entry_kind: EntryKind | None = None,
) -> None:
    # The annotated closure parameter makes the exact frozen request model visible in OpenAPI.
    async def stub(body: Any, _: Any = Depends(require_role(endpoint, entry_kind))):
        del body
        return response_fixture(area, endpoint, response_model)

    stub.__name__ = endpoint.lower().replace(" ", "_").replace("/", "_")
    stub.__annotations__["body"] = request_model
    router.add_api_route(path, stub, methods=["POST"], response_model=response_model)


def add_put(
    router: APIRouter,
    *,
    area: str,
    endpoint: str,
    path: str,
    request_model: type[BaseModel],
    response_model: type[BaseModel],
    query_model: type[BaseModel] | None = None,
) -> None:
    if query_model is None:
        async def stub(body: Any, _: Any = Depends(require_role(endpoint))):
            del body
            return response_fixture(area, endpoint, response_model)
    else:
        async def stub(body: Any, query: Any, _: Any = Depends(require_role(endpoint))):
            del body, query
            return response_fixture(area, endpoint, response_model)

        stub.__annotations__["query"] = Annotated[query_model, Query()]

    stub.__name__ = endpoint.lower().replace(" ", "_").replace("/", "_")
    stub.__annotations__["body"] = request_model
    router.add_api_route(path, stub, methods=["PUT"], response_model=response_model)
