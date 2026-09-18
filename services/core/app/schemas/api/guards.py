"""Shared request and result for the five deterministic output guards."""

from __future__ import annotations

from typing import Any, Literal

from ..common import ContractModel


GuardName = Literal["numbers", "citations", "no-innocence", "extraction", "language"]


class GuardRequest(ContractModel):
    text: str
    context: dict[str, Any]


class OffendingSpan(ContractModel):
    start: int
    end: int
    text: str
    reason: str


class GuardResponse(ContractModel):
    guard: GuardName
    passed: bool
    offending_spans: list[OffendingSpan]


REQUEST_MODELS = (GuardRequest,)

