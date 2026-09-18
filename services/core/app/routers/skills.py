from fastapi import APIRouter, Depends

from ..auth import require_role
from ..db import get_connection
from ..skills.classify_rules import classify
from ..skills.question_budget import select_questions

from ..schemas.api import skills as models
from ._stub import add_post

router = APIRouter(tags=["skills"])


@router.post("/skills/classify-rules", response_model=models.ClassifyRulesResponse)
def rules(body: models.ClassifyRulesRequest, role=Depends(require_role("POST /skills/classify-rules")), connection=Depends(get_connection)):
    return classify(connection, body)


@router.post("/skills/select-questions", response_model=models.SelectQuestionsResponse)
def select(body: models.SelectQuestionsRequest, role=Depends(require_role("POST /skills/select-questions")), connection=Depends(get_connection)):
    return select_questions(connection, body)

for endpoint, path, request, response in (
    ("POST /skills/turnover", "/skills/turnover", models.TurnoverRequest, models.TurnoverResponse),
    ("POST /skills/threshold", "/skills/threshold", models.ThresholdRequest, models.ThresholdResponse),
    ("POST /skills/isolate", "/skills/isolate", models.IsolateRequest, models.IsolateResponse),
    ("POST /skills/tiers", "/skills/tiers", models.TiersRequest, models.TiersResponse),
    ("POST /skills/escalation-check", "/skills/escalation-check", models.EscalationCheckRequest, models.EscalationCheckResponse),
):
    add_post(router, area="skills", endpoint=endpoint, path=path, request_model=request, response_model=response)
