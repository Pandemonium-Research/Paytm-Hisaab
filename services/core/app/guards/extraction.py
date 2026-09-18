"""6.6 extraction guard: figures in structured extraction must appear in the OCR text."""

from __future__ import annotations

from typing import Any

from ..schemas.api.guards import GuardResponse, OffendingSpan
from .figures import collect_numeric_values, iter_figures, values_match


def check_extraction(text: str, context: dict[str, Any]) -> GuardResponse:
    ocr_text = context.get("ocr_text")
    if not ocr_text or not str(ocr_text).strip():
        return GuardResponse(
            guard="extraction",
            passed=False,
            offending_spans=[
                OffendingSpan(
                    start=0,
                    end=len(text),
                    text=text,
                    reason="OCR text is missing or empty; extraction cannot be verified.",
                )
            ],
        )

    allowed = collect_numeric_values(str(ocr_text))
    spans: list[OffendingSpan] = []
    for figure in iter_figures(text):
        if values_match(allowed, figure.value):
            continue
        spans.append(
            OffendingSpan(
                start=figure.start,
                end=figure.end,
                text=figure.text,
                reason=f"Figure {figure.text!r} was not found in the document.",
            )
        )
    return GuardResponse(guard="extraction", passed=not spans, offending_spans=spans)
