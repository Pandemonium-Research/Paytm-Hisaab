from fastapi import APIRouter, Depends

from ..auth import require_role
from ..clock import set_clock
from ..db import get_connection
from ..rails.replay import replay

from ..schemas.api import sim as models
from ..schemas.ledger import EntryKind
from ._stub import add_post

router = APIRouter(tags=["simulator"])


@router.post("/sim/clock", response_model=models.SimClockResponse)
def clock(body: models.SimClockRequest, role=Depends(require_role("POST /sim/clock")), connection=Depends(get_connection)):
    return {"sim_at": set_clock(connection, body.sim_at)}


@router.post("/sim/replay", response_model=models.SimReplayResponse)
def replay_split(body: models.SimReplayRequest, role=Depends(require_role("POST /sim/replay")), connection=Depends(get_connection)):
    return replay(connection, body.split, body.until)

for endpoint, path, request, response, kind in (
    ("POST /sim/reset", "/sim/reset", models.SimResetRequest, models.SimResetResponse, None),
    ("POST /sim/tamper", "/sim/tamper", models.SimTamperRequest, models.SimTamperResponse, None),
    ("POST /anchors/run", "/anchors/run", models.RunAnchorRequest, models.RunAnchorResponse, EntryKind.ANCHOR_CREATED),
):
    add_post(router, area="sim", endpoint=endpoint, path=path, request_model=request, response_model=response, entry_kind=kind)
