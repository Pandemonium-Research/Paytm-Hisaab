from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class StrictRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RememberRequest(StrictRequest):
    merchant_id: str = Field(min_length=1)
    kind: str = Field(min_length=1)
    text: str = Field(min_length=1)
    facts: Any | None = None
    session_id: str | None = None
    index_now: bool = False


class RecallRequest(StrictRequest):
    merchant_id: str = Field(min_length=1)
    query: str = Field(min_length=1)
    session_id: str | None = None
    top_k: int = Field(gt=0, le=100)


class ImproveRequest(StrictRequest):
    merchant_id: str = Field(min_length=1)


class ForgetRequest(StrictRequest):
    merchant_id: str = Field(min_length=1)
    everything: bool = False


class OperationResponse(BaseModel):
    ok: bool
    degraded: bool


class RecallResponse(BaseModel):
    items: list[Any]
    degraded: bool


class HealthResponse(BaseModel):
    ok: bool
    backend: str
    degraded: bool
