from fastapi import APIRouter, BackgroundTasks, Depends

from ..auth import require_role
from ..cases import approvals
from ..cases import serve as artifact_serve
from ..cases.build import build_pack
from ..cases.open import create_case
from ..db import get_connection
from ..ledger.mutations import wire_entry
from ..schemas.api import cases as models
from ..schemas.ledger import EntryKind

router = APIRouter(tags=["cases and packs"])


@router.post("/cases", response_model=models.CreateCaseResponse)
def open_case(
    body: models.CreateCaseRequest,
    role=Depends(require_role("POST /cases", EntryKind.CASE_OPENED)),
    connection=Depends(get_connection, scope="function"),
):
    return create_case(connection, body, role)


@router.post("/packs", response_model=models.BuildPackResponse)
def build(
    body: models.BuildPackRequest,
    role=Depends(require_role("POST /packs", EntryKind.PACK_BUILT)),
    connection=Depends(get_connection, scope="function"),
):
    return build_pack(connection, body, role)


@router.get("/packs/{pack_id}.json")
def pack_json(
    pack_id: str,
    role=Depends(require_role("GET /app/officer/cases/{id}")),
    connection=Depends(get_connection),
):
    return artifact_serve.artifact_response(connection, pack_id, "json")


@router.get("/packs/{pack_id}.pdf")
def pack_pdf(
    pack_id: str,
    role=Depends(require_role("GET /app/officer/cases/{id}")),
    connection=Depends(get_connection),
):
    return artifact_serve.artifact_response(connection, pack_id, "pdf")


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
