from fastapi import APIRouter

from ..schemas.api import ops as models
from ._stub import add_get, add_post

router = APIRouter(tags=["configuration"])

add_post(router, area="ops", endpoint="POST /app/push/subscribe", path="/app/push/subscribe", request_model=models.PushSubscribeRequest, response_model=models.PushSubscribeResponse)
add_get(router, area="ops", endpoint="GET /config", path="/config", response_model=models.ConfigResponse)
