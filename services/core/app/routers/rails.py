from fastapi import APIRouter, Depends

from ..auth import require_role
from ..clock import sim_now
from ..db import get_connection
from ..rails.ingest import ingest_bills, ingest_events, ingest_transactions
from ..schemas.api import rails as models

router = APIRouter(tags=["rails"])


@router.post("/rails/credits", response_model=models.RailsCreditsResponse)
def credits(body: models.RailsCreditsRequest, role=Depends(require_role("POST /rails/credits")), connection=Depends(get_connection)):
    accepted, duplicates = ingest_transactions(connection, body.transactions, body.sim_at or sim_now(connection))
    return {"accepted": accepted, "duplicate_txn_ids": duplicates}


@router.post("/rails/debits", response_model=models.RailsDebitsResponse)
def debits(body: models.RailsDebitsRequest, role=Depends(require_role("POST /rails/debits")), connection=Depends(get_connection)):
    accepted, duplicates = ingest_transactions(connection, body.transactions, body.sim_at or sim_now(connection), debit=True)
    return {"accepted": accepted, "duplicate_txn_ids": duplicates}


@router.post("/rails/bills", response_model=models.RailsBillsResponse)
def bills(body: models.RailsBillsRequest, role=Depends(require_role("POST /rails/bills")), connection=Depends(get_connection)):
    accepted, linked = ingest_bills(connection, body.lines, body.sim_at or sim_now(connection))
    return {"accepted_lines": accepted, "linked_bill_ids": linked}


@router.post("/rails/events", response_model=models.RailsEventsResponse)
def events(body: models.RailsEventsRequest, role=Depends(require_role("POST /rails/events")), connection=Depends(get_connection)):
    return {"accepted": ingest_events(connection, body.events, body.sim_at or sim_now(connection)), "opened_case_ids": []}
