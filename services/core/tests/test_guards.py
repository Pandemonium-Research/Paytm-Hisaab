from __future__ import annotations

import pytest

from app.guards.citations import check_citations
from app.guards.extraction import check_extraction
from app.guards.no_innocence import _INNOCENCE_PATTERNS, check_no_innocence
from app.guards.numbers import check_numbers


VERIFIED_CITE = "Section 2(6), Central Goods and Services Tax Act, 2017"
UNVERIFIED_CITE = (
    "MHA / I4C Standard Operating Procedure for NCRP-CFCFRMS, dated 2 January 2026"
)


def test_numbers_passes_when_figure_is_in_facts() -> None:
    text = "The disputed amount is Rs 4,200."
    response = check_numbers(text, {"facts": {"disputed_amount": 4200}})
    assert response.passed
    assert response.offending_spans == []


def test_numbers_blocks_invented_figure_with_offsets() -> None:
    text = "Turnover was Rs 9,999."
    response = check_numbers(text, {"facts": {"turnover": 4200}})
    assert not response.passed
    span = response.offending_spans[0]
    assert text[span.start : span.end] == span.text == "9,999"
    assert "9,999" in span.reason


def test_numbers_matches_indian_grouping_and_rupee_prefix() -> None:
    text = "Aggregate turnover is ₹ 41,00,000."
    response = check_numbers(text, {"facts": {"aggregate_turnover": 4100000}})
    assert response.passed


def test_numbers_ignores_calendar_date() -> None:
    text = "The notice is dated 21 Mar 2026 for Rs 4,200."
    response = check_numbers(text, {"facts": {"amount": 4200}})
    assert response.passed


def test_numbers_blocks_bare_4200_absent_from_facts() -> None:
    text = "The disputed amount is Rs 4200."
    response = check_numbers(text, {"facts": {"other_amount": 100}})
    assert not response.passed
    span = response.offending_spans[0]
    assert text[span.start : span.end] == span.text == "4200"


def test_numbers_ignores_fy_range_and_calendar_date_without_facts() -> None:
    for text in ("Reporting period FY 2025-26.", "The notice is dated 21 Mar 2026."):
        response = check_numbers(text, {"facts": {}})
        assert response.passed, text


def test_numbers_blocks_bare_year_outside_year_context() -> None:
    text = "Turnover in 2026 exceeded expectations."
    response = check_numbers(text, {"facts": {}})
    assert not response.passed
    span = response.offending_spans[0]
    assert span.text == "2026"


def test_citations_passes_verbatim_verified_cite() -> None:
    text = f"As defined in {VERIFIED_CITE}, turnover includes supplies."
    response = check_citations(text, {})
    assert response.passed


def test_citations_blocks_unverified_verbatim_cite() -> None:
    text = f"The bank relied on {UNVERIFIED_CITE}."
    response = check_citations(text, {})
    assert not response.passed
    span = response.offending_spans[0]
    assert UNVERIFIED_CITE in text[span.start : span.end]
    assert "unverified" in span.reason.lower()


def test_citations_blocks_reworded_cite() -> None:
    text = (
        "The Ministry issued a Standard Operating Procedure for NCRP-CFCFRMS on 2 January 2026."
    )
    response = check_citations(text, {})
    assert not response.passed
    assert any("reworded" in span.reason.lower() for span in response.offending_spans)
    assert any("sop_ncrp_cfcfrms_2026" in span.reason for span in response.offending_spans)


def test_citations_blocks_invented_statute() -> None:
    text = "See Section 99, Imaginary Tax Act, 2024 for relief."
    response = check_citations(text, {})
    assert not response.passed
    span = response.offending_spans[0]
    assert text[span.start : span.end] == span.text
    assert "allowlist" in span.reason.lower()


def test_citations_fails_closed_on_unreadable_file() -> None:
    text = f"Cite {VERIFIED_CITE}."
    response = check_citations(text, {"citations_path": "legal/__missing_citations__.yaml"})
    assert not response.passed
    assert len(response.offending_spans) == 1
    assert response.offending_spans[0].start == 0
    assert response.offending_spans[0].end == len(text)
    assert "Could not load" in response.offending_spans[0].reason


def test_no_innocence_allows_factual_phrasing() -> None:
    allowed = [
        "The merchant states that the payment was for stock.",
        "The records show a POS bill for the disputed credit.",
        "Tier 1 evidence covers the linked bill.",
    ]
    for text in allowed:
        response = check_no_innocence(text, {})
        assert response.passed, text


def test_each_innocence_pattern_blocks() -> None:
    samples = {
        r"\bis innocent\b": "The merchant is innocent.",
        r"\bhas done nothing wrong\b": "The merchant has done nothing wrong.",
        r"\bis a bona fide merchant\b": "She is a bona fide merchant.",
        r"\bis not involved\b": "He is not involved.",
        r"\bis a genuine businessman\b": "He is a genuine businessman.",
        r"\bcommitted no offence\b": "The merchant committed no offence.",
        r"\bcommitted no offense\b": "The merchant committed no offense.",
        r"\bis not a mule\b": "The merchant is not a mule.",
        r"\bclearly did not\b": "The merchant clearly did not participate.",
        r"\bmy client is innocent\b": "My client is innocent.",
        r"\bmy client has done nothing wrong\b": "My client has done nothing wrong.",
        r"\bmy client is not involved\b": "My client is not involved.",
        r"\bthe merchant is innocent\b": "The merchant is innocent.",
        r"\bmerchant is innocent\b": "The merchant is innocent.",
    }
    for pattern, reason in _INNOCENCE_PATTERNS:
        text = samples[pattern.pattern]
        response = check_no_innocence(text, {})
        assert not response.passed, pattern.pattern
        match = pattern.search(text)
        assert match is not None
        span = next(
            item for item in response.offending_spans if item.start == match.start() and item.end == match.end()
        )
        assert text[span.start : span.end] == span.text
        assert span.reason == reason


@pytest.mark.parametrize(
    "text,needle",
    [
        ("The merchant is innocent.", "is innocent"),
        ("She has done nothing wrong in this matter.", "has done nothing wrong"),
        ("My client is not involved in the fraud.", "is not involved"),
    ],
)
def test_no_innocence_blocks_assertions(text: str, needle: str) -> None:
    response = check_no_innocence(text, {})
    assert not response.passed
    span = response.offending_spans[0]
    assert needle.lower() in span.text.lower()
    assert text[span.start : span.end] == span.text


def test_extraction_passes_when_figure_is_in_ocr() -> None:
    text = "Claimed turnover Rs 4,200."
    response = check_extraction(text, {"ocr_text": "Turnover stated as INR 4200 for FY 2025-26."})
    assert response.passed


def test_extraction_blocks_figure_missing_from_ocr() -> None:
    text = "Claimed turnover Rs 9,999."
    response = check_extraction(text, {"ocr_text": "Turnover stated as INR 4200."})
    assert not response.passed
    span = response.offending_spans[0]
    assert text[span.start : span.end] == "9,999"


def test_extraction_blocks_bare_4200_missing_from_ocr() -> None:
    text = "Claimed turnover Rs 4200."
    response = check_extraction(text, {"ocr_text": "Turnover stated as INR 4100."})
    assert not response.passed
    span = response.offending_spans[0]
    assert text[span.start : span.end] == span.text == "4200"


def test_extraction_fails_closed_on_empty_ocr() -> None:
    text = "Claimed turnover Rs 4,200."
    response = check_extraction(text, {"ocr_text": ""})
    assert not response.passed
    assert response.offending_spans[0].start == 0
    assert response.offending_spans[0].end == len(text)
