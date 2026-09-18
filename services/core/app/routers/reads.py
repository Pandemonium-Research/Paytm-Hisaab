from fastapi import APIRouter

from ..schemas.api import reads as models
from ._stub import add_get

router = APIRouter(tags=["reads"])

# Static routes precede dynamic ones so "by-utr" cannot be consumed as a transaction ID.
for endpoint, path, response, query in (
    ("GET /merchants/{id}", "/merchants/{id}", models.MerchantResponse, None),
    ("GET /credits", "/credits", models.CreditsResponse, models.CreditsQuery),
    ("GET /credits/by-utr/{utr}", "/credits/by-utr/{utr}", models.CreditByUtrResponse, None),
    ("GET /credits/{txn}", "/credits/{txn}", models.CreditResponse, None),
    ("GET /payers/{cp}/history", "/payers/{cp}/history", models.PayerHistoryResponse, models.PayerHistoryQuery),
):
    add_get(router, area="reads", endpoint=endpoint, path=path, response_model=response, query_model=query)
