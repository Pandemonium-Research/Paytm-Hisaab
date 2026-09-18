from fastapi import APIRouter

from ..schemas.api import ledger_ops as models
from ..schemas.ledger import EntryKind
from ._stub import add_get, add_post

router = APIRouter(tags=["ledger"])

for endpoint, path, request, response, kind in (
    ("POST /ledger/proposals", "/ledger/proposals", models.LedgerProposalRequest, models.LedgerProposalResponse, EntryKind.LABEL_PROPOSED),
    ("POST /ledger/questions", "/ledger/questions", models.LedgerQuestionRequest, models.LedgerQuestionResponse, EntryKind.QUESTION_ASKED),
    ("POST /ledger/claims", "/ledger/claims", models.LedgerClaimRequest, models.LedgerClaimResponse, EntryKind.CLAIM_ANSWERED),
):
    add_post(router, area="ledger_ops", endpoint=endpoint, path=path, request_model=request, response_model=response, entry_kind=kind)

for endpoint, path, response, query in (
    ("GET /ledger/verify", "/ledger/verify", models.LedgerVerifyResponse, models.LedgerVerifyQuery),
    ("GET /ledger/{m}/entries", "/ledger/{m}/entries", models.LedgerEntriesResponse, models.LedgerEntriesQuery),
    ("GET /anchors", "/anchors", models.AnchorsResponse, models.AnchorsQuery),
):
    add_get(router, area="ledger_ops", endpoint=endpoint, path=path, response_model=response, query_model=query)
