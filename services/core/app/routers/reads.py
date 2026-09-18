from fastapi import APIRouter

from ..schemas.api import reads as models
from ._stub import add_get

router = APIRouter(tags=["reads"])

# Static routes precede dynamic ones so "by-utr" cannot be consumed as a transaction ID.
for endpoint, path, response in (
    ("GET /merchants/{id}", "/merchants/{id}", models.MerchantResponse),
    ("GET /credits", "/credits", models.CreditsResponse),
    ("GET /credits/by-utr/{utr}", "/credits/by-utr/{utr}", models.CreditByUtrResponse),
    ("GET /credits/{txn}", "/credits/{txn}", models.CreditResponse),
    ("GET /payers/{cp}/history", "/payers/{cp}/history", models.PayerHistoryResponse),
):
    add_get(router, area="reads", endpoint=endpoint, path=path, response_model=response)
