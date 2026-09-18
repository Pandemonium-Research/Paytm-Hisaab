from fastapi import APIRouter

from ..schemas.api import app_screens as models
from ._stub import add_get

router = APIRouter(tags=["app screens"])

for endpoint, path, response in (
    ("GET /app/home", "/app/home", models.AppHomeResponse),
    ("GET /app/payments", "/app/payments", models.AppPaymentsResponse),
    ("GET /app/payments/{txn}", "/app/payments/{txn}", models.AppPaymentDetailResponse),
    ("GET /app/cases", "/app/cases", models.AppCasesResponse),
    ("GET /app/turnover", "/app/turnover", models.AppTurnoverResponse),
    ("GET /app/officer/queue", "/app/officer/queue", models.OfficerQueueResponse),
    ("GET /app/officer/cases/{id}", "/app/officer/cases/{id}", models.OfficerCaseResponse),
):
    add_get(router, area="app_screens", endpoint=endpoint, path=path, response_model=response)
