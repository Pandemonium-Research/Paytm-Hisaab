"""Stable record/replay format shared by live clients and local fakes.

Before hashing, normalisation removes timestamp-valued transport metadata, authorisation and
cookie headers, trace/correlation/request/idempotency IDs, signatures, nonces, generated multipart
boundaries, and URL cache-busting query parameters. JSON object keys and query parameters are
sorted; insignificant JSON whitespace is removed; provider payload values, ordered arrays, media
content hashes, model names, prompts, and business-clock values are retained. The request key is
the lowercase SHA-256 hex digest of those canonical normalised request bytes.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Annotated, Literal

from pydantic import AwareDatetime, Field

from .common import ContractModel


class LiveWindow(str, Enum):
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"


class NormalisedRequest(ContractModel):
    method: str
    path: str
    query: dict[str, str | list[str]] = Field(default_factory=dict)
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any = None


class CassetteResponse(ContractModel):
    status: Annotated[int, Field(ge=100, le=599)]
    headers: dict[str, str] = Field(default_factory=dict)
    body: Any


class ProviderCassette(ContractModel):
    schema_version: Literal[1] = 1
    provider: str
    endpoint: str
    request_key: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    normalised_request: NormalisedRequest
    response: CassetteResponse
    live_window: LiveWindow
    recorded_at: AwareDatetime
