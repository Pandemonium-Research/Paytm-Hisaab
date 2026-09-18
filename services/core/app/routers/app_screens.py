from fastapi import APIRouter

from ..schemas.api import app_screens as models
from ._stub import add_get

router = APIRouter(tags=["app screens"])

for endpoint, path, response, query in (
    ("GET /app/home", "/app/home", models.AppHomeResponse, models.MerchantAppQuery),
    ("GET /app/questions", "/app/questions", models.AppQuestionsResponse, models.MerchantAppQuery),
    ("GET /app/payments", "/app/payments", models.AppPaymentsResponse, models.AppPaymentsQuery),
    ("GET /app/payments/{txn}", "/app/payments/{txn}", models.AppPaymentDetailResponse, models.MerchantAppQuery),
    ("GET /app/cases", "/app/cases", models.AppCasesResponse, models.MerchantAppQuery),
    ("GET /app/turnover", "/app/turnover", models.AppTurnoverResponse, models.MerchantAppQuery),
    ("GET /app/officer/queue", "/app/officer/queue", models.OfficerQueueResponse, None),
    ("GET /app/officer/cases/{id}", "/app/officer/cases/{id}", models.OfficerCaseResponse, None),
    ("GET /app/officer/outbox", "/app/officer/outbox", models.OfficerOutboxResponse, None),
):
    add_get(router, area="app_screens", endpoint=endpoint, path=path, response_model=response, query_model=query)
