from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text

from ..auth import require_role
from ..config import get_settings
from ..db import get_connection
from ..ledger.projection import merchant

from ..schemas.api import ops as models
from ._stub import add_post

router = APIRouter(tags=["configuration"])

add_post(router, area="ops", endpoint="POST /app/push/subscribe", path="/app/push/subscribe", request_model=models.PushSubscribeRequest, response_model=models.PushSubscribeResponse)


@router.put("/app/profile", response_model=models.AppProfileResponse)
def profile(body: models.AppProfileRequest, query: Annotated[models.AppProfileQuery, Query()], role=Depends(require_role("PUT /app/profile")), connection=Depends(get_connection)):
    merchant(connection, query.merchant)
    connection.execute(text("""INSERT INTO ops.settings (key, data) VALUES (:key, CAST(:data AS jsonb))
        ON CONFLICT (key) DO UPDATE SET data=excluded.data"""),
        {"key": f"profile:{query.merchant}", "data": body.model_dump_json()})
    return {**body.model_dump(), "saved": True}


@router.get("/config", response_model=models.ConfigResponse)
def config(role=Depends(require_role("GET /config"))):
    settings = get_settings()
    return {"environment": settings.environment, "live": settings.hisaab_live,
        "default_locale": settings.default_locale, "supported_locales": list(settings.supported_locales),
        "vapid_public_key": settings.vapid_public_key}
