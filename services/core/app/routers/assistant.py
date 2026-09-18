from fastapi import APIRouter

from ..schemas.api import assistant as models
from ._stub import add_get, add_post

router = APIRouter(tags=["assistant"])

add_post(router, area="assistant", endpoint="POST /assistant/inbound", path="/assistant/inbound", request_model=models.AssistantInboundRequest, response_model=models.AssistantInboundResponse)
add_get(router, area="assistant", endpoint="GET /assistant/stream", path="/assistant/stream", response_model=models.AssistantStreamResponse)
add_post(router, area="assistant", endpoint="POST /assistant/outbound", path="/assistant/outbound", request_model=models.AssistantOutboundRequest, response_model=models.AssistantOutboundResponse)
