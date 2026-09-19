from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .backends import MemoryBackend, create_backend
from .models import (
    ForgetRequest,
    HealthResponse,
    ImproveRequest,
    OperationResponse,
    RecallRequest,
    RecallResponse,
    RememberRequest,
)


logger = logging.getLogger(__name__)

app = FastAPI(title="Hisaab memory", version="0.1.0")
app.state.backend = create_backend()


def _backend(request: Request) -> MemoryBackend:
    return request.app.state.backend


def _backend_failed(operation: str, backend: MemoryBackend, error: Exception) -> None:
    # Deliberately omit exception text: provider errors can contain request material or secrets.
    logger.warning(
        "memory backend call failed: operation=%s backend=%s error_type=%s",
        operation,
        backend.name,
        type(error).__name__,
    )


async def _operation(
    request: Request,
    name: str,
    call: Callable[[MemoryBackend], Awaitable[None]],
) -> OperationResponse:
    backend = _backend(request)
    try:
        await call(backend)
    except Exception as error:
        _backend_failed(name, backend, error)
        return OperationResponse(ok=False, degraded=True)
    return OperationResponse(ok=True, degraded=False)


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, error: RequestValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"detail": jsonable_encoder(error.errors()), "degraded": False},
    )


@app.exception_handler(StarletteHTTPException)
async def http_error(_request: Request, error: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=error.status_code,
        content={"detail": error.detail, "degraded": False},
    )


@app.exception_handler(Exception)
async def unexpected_error(_request: Request, error: Exception) -> JSONResponse:
    logger.error("unexpected memory service error: error_type=%s", type(error).__name__)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal service error", "degraded": False},
    )


@app.post("/remember", response_model=OperationResponse)
async def remember(body: RememberRequest, request: Request) -> OperationResponse:
    async def remember_and_optionally_index(backend: MemoryBackend) -> None:
        await backend.remember(body)
        if body.index_now:
            await backend.improve(body.merchant_id)

    return await _operation(request, "remember", remember_and_optionally_index)


@app.post("/recall", response_model=RecallResponse)
async def recall(body: RecallRequest, request: Request) -> RecallResponse:
    backend = _backend(request)
    try:
        items = await backend.recall(body)
    except Exception as error:
        _backend_failed("recall", backend, error)
        return RecallResponse(items=[], degraded=True)
    return RecallResponse(items=items, degraded=False)


@app.post("/improve", response_model=OperationResponse)
async def improve(body: ImproveRequest, request: Request) -> OperationResponse:
    return await _operation(
        request,
        "improve",
        lambda backend: backend.improve(body.merchant_id),
    )


@app.post("/forget", response_model=OperationResponse)
async def forget(body: ForgetRequest, request: Request) -> OperationResponse:
    return await _operation(request, "forget", lambda backend: backend.forget(body))


def _health(request: Request) -> HealthResponse:
    return HealthResponse(ok=True, backend=_backend(request).name, degraded=False)


@app.get("/health", response_model=HealthResponse)
async def health(request: Request) -> HealthResponse:
    return _health(request)


@app.get("/healthz", response_model=HealthResponse, include_in_schema=False)
async def healthz(request: Request) -> HealthResponse:
    return _health(request)
