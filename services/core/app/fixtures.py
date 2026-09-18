"""Validated response fixtures for the Phase 2A stub API."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import BaseModel


FIXTURE_DIR = Path(__file__).with_name("fixtures")


@lru_cache
def _area(area: str) -> dict[str, Any]:
    path = FIXTURE_DIR / f"{area}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def response_fixture(area: str, endpoint: str, model: type[BaseModel]) -> dict[str, Any]:
    """Load and validate before FastAPI serialises the fixture."""

    return model.model_validate(_area(area)[endpoint]).model_dump(mode="json")
