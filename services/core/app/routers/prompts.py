from fastapi import APIRouter

from ..schemas.api import prompts as models
from ._stub import add_get

router = APIRouter(tags=["prompts"])

add_get(router, area="prompts", endpoint="GET /prompts/{name}", path="/prompts/{name}", response_model=models.PromptResponse)
