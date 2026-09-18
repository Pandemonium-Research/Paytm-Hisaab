from fastapi import APIRouter, BackgroundTasks, Depends

from ..auth import require_role
from ..cases import approvals
from ..db import get_connection
from ..ledger.mutations import wire_entry
from ..schemas.api import cases as models
from ..schemas.ledger import EntryKind
from ._stub import add_post

router = APIRouter(tags=["cases and packs"])

# 6.8 builds the pack JSON and PDF; until then these two return fixtures.
for endpoint, path, request, response, kind in (
    ("POST /cases", "/cases", models.CreateCaseRequest, models.CreateCaseResponse, EntryKind.CASE_OPENED),
    ("POST /packs", "/packs", models.BuildPackRequest, models.BuildPackResponse, EntryKind.PACK_BUILT),
):
    add_post(router, area="cases", endpoint=endpoint, path=path, request_model=request, response_model=response, entry_kind=kind)


# The decision routes use scope="function" for the same reason as POST /rails/events: the resume
# must reach the waiting workflow only after the decision has committed, or WF20 re-reads core and
# finds nothing. `workflow_resumed` therefore reports that a resume was scheduled for after commit,
# since its delivery happens once the response has gone (D38).
def decision(pack_id, body, role, connection, background, *, approve):
    entry, resume_url = approvals.decide(connection, pack_id, body, role, approve=approve)
    status = "approved" if approve else "rejected"
    if resume_url:
        background.add_task(approvals.resume, resume_url, {"pack_id": pack_id, "decision": status, "entry_seq": entry.root.seq})
    return {"pack_id": pack_id, "status": status, "workflow_resumed": resume_url is not None, "ledger_entry": wire_entry(entry)}


@router.post("/packs/{id}/approve", response_model=models.ApprovePackResponse)
def approve(id: str, body: models.ApprovePackRequest, background: BackgroundTasks,
            role=Depends(require_role("POST /packs/{id}/approve", EntryKind.PACK_APPROVED)),
            connection=Depends(get_connection, scope="function")):
    return decision(id, body, role, connection, background, approve=True)


@router.post("/packs/{id}/reject", response_model=models.RejectPackResponse)
def reject(id: str, body: models.RejectPackRequest, background: BackgroundTasks,
           role=Depends(require_role("POST /packs/{id}/reject", EntryKind.PACK_REJECTED)),
           connection=Depends(get_connection, scope="function")):
    return decision(id, body, role, connection, background, approve=False)


@router.post("/outbox/{pack}/send", response_model=models.SendPackResponse)
def send(pack: str, body: models.SendPackRequest,
         role=Depends(require_role("POST /outbox/{pack}/send", EntryKind.PACK_SENT)),
         connection=Depends(get_connection)):
    entry, delivery_ref = approvals.send(connection, pack, body, role)
    return {"pack_id": pack, "sent": True, "delivery_ref": delivery_ref, "simulated": True, "ledger_entry": wire_entry(entry)}
