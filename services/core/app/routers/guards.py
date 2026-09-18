from fastapi import APIRouter, Depends

from ..auth import require_role
from ..guards.citations import check_citations
from ..guards.extraction import check_extraction
from ..guards.no_innocence import check_no_innocence
from ..guards.numbers import check_numbers
from ..schemas.api import guards as models
from ._stub import add_post

router = APIRouter(tags=["guards"])


@router.post("/guards/numbers", response_model=models.GuardResponse)
def numbers(body: models.GuardRequest, _=Depends(require_role("POST /guards/numbers"))):
    return check_numbers(body.text, body.context)


@router.post("/guards/citations", response_model=models.GuardResponse)
def citations(body: models.GuardRequest, _=Depends(require_role("POST /guards/citations"))):
    return check_citations(body.text, body.context)


@router.post("/guards/no-innocence", response_model=models.GuardResponse)
def no_innocence(body: models.GuardRequest, _=Depends(require_role("POST /guards/no-innocence"))):
    return check_no_innocence(body.text, body.context)


@router.post("/guards/extraction", response_model=models.GuardResponse)
def extraction(body: models.GuardRequest, _=Depends(require_role("POST /guards/extraction"))):
    return check_extraction(body.text, body.context)


add_post(
    router,
    area="guards",
    endpoint="POST /guards/language",
    path="/guards/language",
    request_model=models.GuardRequest,
    response_model=models.GuardResponse,
)
