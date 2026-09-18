"""In-app assistant ingress, event-stream and egress contracts."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from ..common import ContractModel, MerchantId


class AssistantStreamQuery(ContractModel):
    merchant: Annotated[
        MerchantId, Field(description="Merchant whose assistant events to stream.")
    ]


class AssistantContentType(str, Enum):
    TEXT = "text"
    AUDIO = "audio"
    IMAGE = "image"
    PDF = "pdf"


class AssistantInboundRequest(ContractModel):
    merchant_id: MerchantId
    message_id: str
    content_type: AssistantContentType
    text: str | None = None
    media_url: str | None = None
    media_sha256: str | None = None
    language: str | None = None
    sim_at: AwareDatetime


class AssistantInboundResponse(ContractModel):
    accepted: bool
    conversation_id: str
    forwarded_to_workflow: bool


class AssistantEvent(ContractModel):
    event_id: str
    event: Literal["message", "status", "error"]
    data: str


class AssistantStreamResponse(ContractModel):
    """Shape of each SSE event; the HTTP response is an event stream."""

    event: AssistantEvent


class AssistantOutboundRequest(ContractModel):
    merchant_id: MerchantId
    conversation_id: str
    text: str
    language: str
    in_reply_to: str | None = None
    sim_at: AwareDatetime


class AssistantOutboundResponse(ContractModel):
    message_id: str
    published: bool


REQUEST_MODELS = (AssistantInboundRequest, AssistantOutboundRequest)
