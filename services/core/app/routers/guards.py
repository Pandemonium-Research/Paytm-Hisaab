from fastapi import APIRouter

from ..schemas.api import guards as models
from ._stub import add_post

router = APIRouter(tags=["guards"])

for name in ("numbers", "citations", "no-innocence", "extraction", "language"):
    endpoint = f"POST /guards/{name}"
    add_post(router, area="guards", endpoint=endpoint, path=f"/guards/{name}", request_model=models.GuardRequest, response_model=models.GuardResponse)
