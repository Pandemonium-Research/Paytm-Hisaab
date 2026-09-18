from fastapi import APIRouter

from ..schemas.api import sim as models
from ..schemas.ledger import EntryKind
from ._stub import add_post

router = APIRouter(tags=["simulator"])

for endpoint, path, request, response, kind in (
    ("POST /sim/clock", "/sim/clock", models.SimClockRequest, models.SimClockResponse, None),
    ("POST /sim/replay", "/sim/replay", models.SimReplayRequest, models.SimReplayResponse, None),
    ("POST /sim/reset", "/sim/reset", models.SimResetRequest, models.SimResetResponse, None),
    ("POST /sim/tamper", "/sim/tamper", models.SimTamperRequest, models.SimTamperResponse, None),
    ("POST /anchors/run", "/anchors/run", models.RunAnchorRequest, models.RunAnchorResponse, EntryKind.ANCHOR_CREATED),
):
    add_post(router, area="sim", endpoint=endpoint, path=path, request_model=request, response_model=response, entry_kind=kind)
