"""6.6 numbers guard: every figure in generated text must appear in the facts payload.

Ignored in text (not treated as monetary/count claims): calendar dates such as ``21 Mar 2026`` or
``2026-03-21``, clock times such as ``7:47 PM``, bare ``1900``–``2100`` tokens only when they sit
in a date or year context (``FY 2025-26``, ``financial year 2024``, and similar cues), and a
numbered list marker at the start of a line (``1.`` or ``1)``). Comma-grouped amounts are always
figures.
"""

from __future__ import annotations

from typing import Any

from ..schemas.api.guards import GuardResponse, OffendingSpan
from .figures import collect_numeric_values, iter_figures, values_match


def check_numbers(text: str, context: dict[str, Any]) -> GuardResponse:
    allowed = collect_numeric_values(context.get("facts"))
    spans: list[OffendingSpan] = []
    for figure in iter_figures(text):
        if values_match(allowed, figure.value):
            continue
        spans.append(
            OffendingSpan(
                start=figure.start,
                end=figure.end,
                text=figure.text,
                reason=f"Figure {figure.text!r} is not present in the facts payload.",
            )
        )
    return GuardResponse(guard="numbers", passed=not spans, offending_spans=spans)
