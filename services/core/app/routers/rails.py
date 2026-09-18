from fastapi import APIRouter

from ..schemas.api import rails as models
from ..schemas.ledger import EntryKind
from ._stub import add_post

router = APIRouter(tags=["rails"])

for endpoint, path, request, response, kind in (
    ("POST /rails/credits", "/rails/credits", models.RailsCreditsRequest, models.RailsCreditsResponse, EntryKind.CREDIT_OBSERVED),
    ("POST /rails/bills", "/rails/bills", models.RailsBillsRequest, models.RailsBillsResponse, EntryKind.BILL_LINKED),
    ("POST /rails/events", "/rails/events", models.RailsEventsRequest, models.RailsEventsResponse, EntryKind.CASE_OPENED),
):
    add_post(router, area="rails", endpoint=endpoint, path=path, request_model=request, response_model=response, entry_kind=kind)
