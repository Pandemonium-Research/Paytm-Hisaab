from fastapi import APIRouter, Depends

from ..auth import require_role
from ..db import get_connection
from ..skills.classify_rules import classify
from ..skills.isolate import isolate
from ..skills.question_budget import select_questions
from ..skills.tiers import tiers
from ..skills.threshold import threshold
from ..skills.turnover import turnover

from ..schemas.api import skills as models
from ._stub import add_post

router = APIRouter(tags=["skills"])


@router.post("/skills/classify-rules", response_model=models.ClassifyRulesResponse)
def rules(body: models.ClassifyRulesRequest, role=Depends(require_role("POST /skills/classify-rules")), connection=Depends(get_connection)):
    return classify(connection, body)


@router.post("/skills/select-questions", response_model=models.SelectQuestionsResponse)
def select(body: models.SelectQuestionsRequest, role=Depends(require_role("POST /skills/select-questions")), connection=Depends(get_connection)):
    return select_questions(connection, body)


@router.post("/skills/isolate", response_model=models.IsolateResponse)
def isolation(body: models.IsolateRequest, role=Depends(require_role("POST /skills/isolate")), connection=Depends(get_connection)):
    return isolate(connection, body)


@router.post("/skills/tiers", response_model=models.TiersResponse)
def evidence_tiers(body: models.TiersRequest, role=Depends(require_role("POST /skills/tiers")), connection=Depends(get_connection)):
    return tiers(connection, body)


@router.post("/skills/turnover", response_model=models.TurnoverResponse)
def turnover_skill(body: models.TurnoverRequest, role=Depends(require_role("POST /skills/turnover")), connection=Depends(get_connection)):
    return turnover(connection, body)


@router.post("/skills/threshold", response_model=models.ThresholdResponse)
def threshold_skill(body: models.ThresholdRequest, role=Depends(require_role("POST /skills/threshold")), connection=Depends(get_connection)):
    return threshold(connection, body)


for endpoint, path, request, response in (
    ("POST /skills/escalation-check", "/skills/escalation-check", models.EscalationCheckRequest, models.EscalationCheckResponse),
):
    add_post(router, area="skills", endpoint=endpoint, path=path, request_model=request, response_model=response)
