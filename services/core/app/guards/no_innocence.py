"""6.6 no-innocence guard: block factual assertions of merchant innocence or bona fides."""

from __future__ import annotations

import re
from typing import Any

from ..schemas.api.guards import GuardResponse, OffendingSpan

_INNOCENCE_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bis innocent\b", re.I), "The text asserts innocence as fact."),
    (re.compile(r"\bhas done nothing wrong\b", re.I), "The text asserts the merchant did nothing wrong as fact."),
    (re.compile(r"\bis a bona fide merchant\b", re.I), "The text asserts bona fides as fact."),
    (re.compile(r"\bis not involved\b", re.I), "The text denies involvement as fact."),
    (re.compile(r"\bis a genuine businessman\b", re.I), "The text asserts good faith as fact."),
    (re.compile(r"\bcommitted no offence\b", re.I), "The text asserts no offence was committed as fact."),
    (re.compile(r"\bcommitted no offense\b", re.I), "The text asserts no offense was committed as fact."),
    (re.compile(r"\bis not a mule\b", re.I), "The text denies mule activity as fact."),
    (re.compile(r"\bclearly did not\b", re.I), "The text asserts exculpation as fact."),
    (re.compile(r"\bmy client is innocent\b", re.I), "The text asserts the client's innocence as fact."),
    (re.compile(r"\bmy client has done nothing wrong\b", re.I), "The text asserts the client did nothing wrong as fact."),
    (re.compile(r"\bmy client is not involved\b", re.I), "The text denies the client's involvement as fact."),
    (re.compile(r"\bthe merchant is innocent\b", re.I), "The text asserts the merchant's innocence as fact."),
    (re.compile(r"\bmerchant is innocent\b", re.I), "The text asserts the merchant's innocence as fact."),
]

_ATTRIBUTION = re.compile(
    r"(the merchant states that|the records show|tier\s+\d+\s+evidence)",
    re.I,
)


def _attributed_claim(text: str, start: int) -> bool:
    window = text[max(0, start - 120) : start]
    return bool(_ATTRIBUTION.search(window))


def check_no_innocence(text: str, context: dict[str, Any]) -> GuardResponse:
    del context
    spans: list[OffendingSpan] = []
    for pattern, reason in _INNOCENCE_PATTERNS:
        for match in pattern.finditer(text):
            if _attributed_claim(text, match.start()):
                continue
            spans.append(
                OffendingSpan(
                    start=match.start(),
                    end=match.end(),
                    text=text[match.start() : match.end()],
                    reason=reason,
                )
            )
    return GuardResponse(guard="no-innocence", passed=not spans, offending_spans=spans)
