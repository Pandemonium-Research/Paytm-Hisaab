"""Versioned prompt read contract."""

from __future__ import annotations

from ..common import ContractModel


class PromptResponse(ContractModel):
    name: str
    version: str
    text: str
    sha256: str


REQUEST_MODELS: tuple[type[ContractModel], ...] = ()

