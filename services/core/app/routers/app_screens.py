from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ..auth import require_role
from ..db import get_connection
from ..ops import screens

from ..schemas.api import app_screens as models
from ._stub import add_get

router = APIRouter(tags=["app screens"])


@router.get("/app/home", response_model=models.AppHomeResponse)
def home(query: Annotated[models.MerchantAppQuery, Query()], role=Depends(require_role("GET /app/home")), connection=Depends(get_connection)):
    return screens.home(connection, query.merchant)


@router.get("/app/questions", response_model=models.AppQuestionsResponse)
def questions(query: Annotated[models.MerchantAppQuery, Query()], role=Depends(require_role("GET /app/questions")), connection=Depends(get_connection)):
    return screens.questions(connection, query.merchant)


@router.get("/app/payments", response_model=models.AppPaymentsResponse)
def payments(query: Annotated[models.AppPaymentsQuery, Query()], role=Depends(require_role("GET /app/payments")), connection=Depends(get_connection)):
    return screens.payments(connection, query.merchant, query.limit, query.cursor)


@router.get("/app/payments/{txn}", response_model=models.AppPaymentDetailResponse)
def payment(txn: str, query: Annotated[models.MerchantAppQuery, Query()], role=Depends(require_role("GET /app/payments/{txn}")), connection=Depends(get_connection)):
    return screens.payment_detail(connection, query.merchant, txn)

for endpoint, path, response, query in (
    ("GET /app/cases", "/app/cases", models.AppCasesResponse, models.MerchantAppQuery),
    ("GET /app/turnover", "/app/turnover", models.AppTurnoverResponse, models.MerchantAppQuery),
    ("GET /app/officer/queue", "/app/officer/queue", models.OfficerQueueResponse, None),
    ("GET /app/officer/cases/{id}", "/app/officer/cases/{id}", models.OfficerCaseResponse, None),
    ("GET /app/officer/outbox", "/app/officer/outbox", models.OfficerOutboxResponse, None),
):
    add_get(router, area="app_screens", endpoint=endpoint, path=path, response_model=response, query_model=query)
