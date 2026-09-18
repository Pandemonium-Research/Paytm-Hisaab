from fastapi import APIRouter

from ..schemas.api import skills as models
from ._stub import add_post

router = APIRouter(tags=["skills"])

for endpoint, path, request, response in (
    ("POST /skills/classify-rules", "/skills/classify-rules", models.ClassifyRulesRequest, models.ClassifyRulesResponse),
    ("POST /skills/select-questions", "/skills/select-questions", models.SelectQuestionsRequest, models.SelectQuestionsResponse),
    ("POST /skills/turnover", "/skills/turnover", models.TurnoverRequest, models.TurnoverResponse),
    ("POST /skills/threshold", "/skills/threshold", models.ThresholdRequest, models.ThresholdResponse),
    ("POST /skills/isolate", "/skills/isolate", models.IsolateRequest, models.IsolateResponse),
    ("POST /skills/tiers", "/skills/tiers", models.TiersRequest, models.TiersResponse),
    ("POST /skills/escalation-check", "/skills/escalation-check", models.EscalationCheckRequest, models.EscalationCheckResponse),
):
    add_post(router, area="skills", endpoint=endpoint, path=path, request_model=request, response_model=response)
