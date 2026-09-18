import json
import os
import urllib.error
import urllib.request
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text

from ..auth import require_role
from ..db import get_connection
from ..ledger.mutations import validate_time
from ..ledger.projection import merchant

from ..schemas.api import assistant as models
from ._stub import add_get

router = APIRouter(tags=["assistant"])

def forward(body):
    url = os.getenv("N8N_ASSISTANT_WEBHOOK_URL", "http://n8n:5678/webhook/hisaab/wf31-assistant")
    request = urllib.request.Request(url, data=body.model_dump_json().encode(), headers={
        "Content-Type": "application/json",
        "X-N8N-Webhook-Secret": os.getenv("N8N_WEBHOOK_SECRET", "dev-webhook-secret"),
    })
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            response.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise HTTPException(502, "The assistant workflow is unavailable; retry this question.") from exc


@router.post("/assistant/inbound", response_model=models.AssistantInboundResponse)
def inbound(body: models.AssistantInboundRequest, role=Depends(require_role("POST /assistant/inbound")), connection=Depends(get_connection)):
    merchant(connection, body.merchant_id)
    validate_time(connection, body.sim_at)
    forward(body)
    return {"accepted": True, "conversation_id": f"wf31-{body.merchant_id}", "forwarded_to_workflow": True}


add_get(router, area="assistant", endpoint="GET /assistant/stream", path="/assistant/stream", response_model=models.AssistantStreamResponse, query_model=models.AssistantStreamQuery)


@router.post("/assistant/outbound", response_model=models.AssistantOutboundResponse)
def outbound(body: models.AssistantOutboundRequest, role=Depends(require_role("POST /assistant/outbound")), connection=Depends(get_connection)):
    merchant(connection, body.merchant_id)
    validate_time(connection, body.sim_at)
    connection.execute(text("""INSERT INTO ops.conversations (conversation_id, merchant_id, data)
        VALUES (:id, :merchant, '{"messages": []}'::jsonb)
        ON CONFLICT (conversation_id) DO NOTHING"""),
        {"id": body.conversation_id, "merchant": body.merchant_id})
    conversation = connection.execute(text("SELECT * FROM ops.conversations WHERE conversation_id=:id FOR UPDATE"),
        {"id": body.conversation_id}).mappings().one()
    if conversation["merchant_id"] != body.merchant_id:
        raise HTTPException(409, "The conversation belongs to another merchant.")
    message = {**body.model_dump(mode="json"), "message_id": f"MSG-{uuid4().hex}"}
    data = {**conversation["data"], "messages": [*conversation["data"].get("messages", []), message]}
    connection.execute(text("UPDATE ops.conversations SET data=CAST(:data AS jsonb) WHERE conversation_id=:id"),
        {"id": body.conversation_id, "data": json.dumps(data)})
    return {"message_id": message["message_id"], "published": True}
