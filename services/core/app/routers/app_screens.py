from typing import Annotated

from fastapi import APIRouter, Depends, Query

from ..auth import require_role
from ..db import get_connection
from ..cases import reads as case_reads
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


@router.get("/app/cases", response_model=models.AppCasesResponse)
def cases(query: Annotated[models.MerchantAppQuery, Query()], role=Depends(require_role("GET /app/cases")), connection=Depends(get_connection)):
    return case_reads.merchant_cases(connection, query.merchant)


@router.get("/app/officer/queue", response_model=models.OfficerQueueResponse)
def officer_queue(role=Depends(require_role("GET /app/officer/queue")), connection=Depends(get_connection)):
    return case_reads.officer_queue(connection)


@router.get("/app/officer/cases/{id}", response_model=models.OfficerCaseResponse)
def officer_case(id: str, role=Depends(require_role("GET /app/officer/cases/{id}")), connection=Depends(get_connection)):
    return case_reads.officer_case(connection, id)


@router.get("/app/officer/outbox", response_model=models.OfficerOutboxResponse)
def officer_outbox(role=Depends(require_role("GET /app/officer/outbox")), connection=Depends(get_connection)):
    return case_reads.officer_outbox(connection)

for endpoint, path, response, query in (
    ("GET /app/turnover", "/app/turnover", models.AppTurnoverResponse, models.MerchantAppQuery),
):
    add_get(router, area="app_screens", endpoint=endpoint, path=path, response_model=response, query_model=query)
