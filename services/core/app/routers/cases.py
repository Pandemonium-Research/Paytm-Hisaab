from fastapi import APIRouter

from ..schemas.api import cases as models
from ..schemas.ledger import EntryKind
from ._stub import add_post

router = APIRouter(tags=["cases and packs"])

for endpoint, path, request, response, kind in (
    ("POST /cases", "/cases", models.CreateCaseRequest, models.CreateCaseResponse, EntryKind.CASE_OPENED),
    ("POST /packs", "/packs", models.BuildPackRequest, models.BuildPackResponse, EntryKind.PACK_BUILT),
    ("POST /packs/{id}/approve", "/packs/{id}/approve", models.ApprovePackRequest, models.ApprovePackResponse, EntryKind.PACK_APPROVED),
    ("POST /packs/{id}/reject", "/packs/{id}/reject", models.RejectPackRequest, models.RejectPackResponse, EntryKind.PACK_REJECTED),
    ("POST /outbox/{pack}/send", "/outbox/{pack}/send", models.SendPackRequest, models.SendPackResponse, EntryKind.PACK_SENT),
):
    add_post(router, area="cases", endpoint=endpoint, path=path, request_model=request, response_model=response, entry_kind=kind)
