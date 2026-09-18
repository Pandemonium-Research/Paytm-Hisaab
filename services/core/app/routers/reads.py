from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

from ..auth import require_role
from ..clock import sim_now
from ..db import get_connection
from ..ledger.projection import merchant, read_credit, read_credits
from ..schemas.api import reads as models
from ..skills.payer_history import payer_history

router = APIRouter(tags=["reads"])


@router.get("/merchants/{id}", response_model=models.MerchantResponse)
def get_merchant(id: str, role=Depends(require_role("GET /merchants/{id}")), connection=Depends(get_connection)):
    return merchant(connection, id)


@router.get("/credits", response_model=models.CreditsResponse)
def get_credits(query: Annotated[models.CreditsQuery, Query()], role=Depends(require_role("GET /credits")), connection=Depends(get_connection)):
    as_of = query.as_of or sim_now(connection)
    items, cursor = read_credits(connection, query.merchant, as_of, query.limit, query.cursor)
    return {"items": items, "next_cursor": cursor, "as_of": as_of}


@router.get("/credits/by-utr/{utr}", response_model=models.CreditByUtrResponse)
def get_utr(utr: str, role=Depends(require_role("GET /credits/by-utr/{utr}")), connection=Depends(get_connection)):
    as_of = sim_now(connection)
    transactions = connection.execute(text("SELECT txn_id FROM rails.credits WHERE utr = :utr AND ts <= :as_of"), {"utr": utr, "as_of": as_of}).scalars().all()
    if not transactions:
        raise HTTPException(404, "No payment has this UTR at the current business time.")
    if len(transactions) != 1:
        raise HTTPException(409, "More than one payment has this UTR.")
    return read_credit(connection, transactions[0], as_of)


@router.get("/credits/{txn}", response_model=models.CreditResponse)
def get_credit(txn: str, role=Depends(require_role("GET /credits/{txn}")), connection=Depends(get_connection)):
    return read_credit(connection, txn, sim_now(connection))


@router.get("/payers/{cp}/history", response_model=models.PayerHistoryResponse)
def get_history(cp: str, query: Annotated[models.PayerHistoryQuery, Query()], role=Depends(require_role("GET /payers/{cp}/history")), connection=Depends(get_connection)):
    return payer_history(connection, query.merchant, cp, query.as_of or sim_now(connection))
