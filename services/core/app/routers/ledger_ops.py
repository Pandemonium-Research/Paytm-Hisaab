from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from ..auth import require_role
from ..db import get_connection
from ..ledger import mutations
from ..ledger.verify import verify

from ..schemas.api import ledger_ops as models
from ..schemas.ledger import LedgerEntry
from ._stub import add_get

router = APIRouter(tags=["ledger"])

@router.post("/ledger/proposals", response_model=models.LedgerProposalResponse)
def proposal(body: models.LedgerProposalRequest, role=Depends(require_role("POST /ledger/proposals")), connection=Depends(get_connection)):
    return {"entry": mutations.wire_entry(mutations.proposal(connection, body, role))}


@router.post("/ledger/questions", response_model=models.LedgerQuestionResponse)
def question(body: models.LedgerQuestionRequest, role=Depends(require_role("POST /ledger/questions")), connection=Depends(get_connection)):
    return {"entry": mutations.wire_entry(mutations.question(connection, body, role))}


@router.post("/ledger/claims", response_model=models.LedgerClaimResponse)
def claim(body: models.LedgerClaimRequest, role=Depends(require_role("POST /ledger/claims")), connection=Depends(get_connection)):
    entry, updated = mutations.claim(connection, body, role)
    return {"entry": mutations.wire_entry(entry), "payer_fact_updated": updated}


@router.get("/ledger/verify", response_model=models.LedgerVerifyResponse)
def verify_chain(query: Annotated[models.LedgerVerifyQuery, Query()], role=Depends(require_role("GET /ledger/verify")), connection=Depends(get_connection)):
    return verify(connection, query.merchant)


@router.get("/ledger/{m}/entries", response_model=models.LedgerEntriesResponse)
def entries(m: str, query: Annotated[models.LedgerEntriesQuery, Query()], role=Depends(require_role("GET /ledger/{m}/entries")), connection=Depends(get_connection)):
    try:
        cursor = int(query.cursor) if query.cursor else -1
        if cursor < -1:
            raise ValueError()
    except ValueError as exc:
        raise HTTPException(422, "Use the next_cursor returned by the ledger endpoint.") from exc
    rows = connection.execute(text("SELECT * FROM ledger.entries WHERE merchant_id = :merchant AND chain_index > :cursor ORDER BY chain_index LIMIT :limit"),
        {"merchant": m, "cursor": cursor, "limit": query.limit + 1}).mappings().all()
    page = rows[:query.limit]
    return {"entries": [mutations.wire_entry(LedgerEntry.model_validate(dict(row))) for row in page],
            "next_cursor": str(page[-1]["chain_index"]) if len(rows) > query.limit else None}

for endpoint, path, response, query in (
    ("GET /anchors", "/anchors", models.AnchorsResponse, models.AnchorsQuery),
):
    add_get(router, area="ledger_ops", endpoint=endpoint, path=path, response_model=response, query_model=query)
