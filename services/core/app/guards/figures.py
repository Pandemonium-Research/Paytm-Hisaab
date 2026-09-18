"""Parse monetary and count figures from text; compare by numeric value."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_INDIC_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

_MONTHS = (
    "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
    "|january|february|march|april|june|july|august|september|october|november|december"
)

_FIGURE = re.compile(
    r"""
    (?:
        ₹\s*
        (?P<rupee>[\d,\u0966-\u096f]+(?:\.\d+)?(?:\s*(?:L|lakh|Cr|crore))?)
        |
        (?P<plain>[\d,\u0966-\u096f]+(?:\.\d+)?)\s*(?P<pct>%)
        |
        (?P<amount>[\d,\u0966-\u096f]+(?:\.\d+)?)\s*(?P<suffix>L|lakh|Cr|crore)\b
        |
        (?P<number>[\d,\u0966-\u096f]+(?:\.\d+)?)
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)

_DATE_TEXT = re.compile(rf"\b\d{{1,2}}\s+(?:{_MONTHS})\s+\d{{4}}\b", re.IGNORECASE)
_ISO_DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")
_TIME = re.compile(r"\b\d{1,2}:\d{2}\s*(?:AM|PM)?\b", re.IGNORECASE)
_LINE_INDEX = re.compile(r"(?m)^\s*\d+[.)]\s")
_YEAR_TOKEN = r"(?:19\d{2}|20\d{2}|21\d{2})"
_YEAR_RANGE_TAIL = r"(?:-\d{2}|-" + _YEAR_TOKEN + r")"
_FY_AY_YEAR = re.compile(
    rf"\b(?:FY|AY)\s+{_YEAR_TOKEN}{_YEAR_RANGE_TAIL}?\b",
    re.IGNORECASE,
)
_FINANCIAL_YEAR = re.compile(
    rf"\bfinancial\s+year\s+{_YEAR_TOKEN}{_YEAR_RANGE_TAIL}?\b",
    re.IGNORECASE,
)
_YEAR_LABEL = re.compile(rf"\byear\s+{_YEAR_TOKEN}\b", re.IGNORECASE)


@dataclass(frozen=True)
class FigureSpan:
    start: int
    end: int
    text: str
    value: float


def _normalize_digits(raw: str) -> str:
    return raw.translate(_INDIC_DIGITS)


def _parse_numeric_token(raw: str) -> float:
    cleaned = _normalize_digits(raw).replace(",", "")
    return float(cleaned)


def _apply_multiplier(base: float, suffix: str | None) -> float:
    if suffix is None:
        return base
    key = suffix.lower()
    if key in {"l", "lakh"}:
        return base * 100_000
    if key in {"cr", "crore"}:
        return base * 10_000_000
    return base


def parse_figure_value(raw: str, suffix: str | None = None) -> float:
    return _apply_multiplier(_parse_numeric_token(raw), suffix)


def values_match(allowed: set[float], value: float) -> bool:
    for candidate in allowed:
        if abs(candidate - value) <= max(1e-9, abs(value) * 1e-9):
            return True
        if value == int(value) and candidate == int(candidate) and int(value) == int(candidate):
            return True
    return False


def _ignored_ranges(text: str) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for pattern in (
        _DATE_TEXT,
        _ISO_DATE,
        _TIME,
        _LINE_INDEX,
        _FY_AY_YEAR,
        _FINANCIAL_YEAR,
        _YEAR_LABEL,
    ):
        for match in pattern.finditer(text):
            ranges.append((match.start(), match.end()))
    return ranges


def _inside_range(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(start >= left and end <= right for left, right in ranges)


def _is_embedded_in_longer_digit_run(text: str, start: int, end: int) -> bool:
    if start > 0 and text[start - 1].isdigit():
        return True
    if end < len(text) and text[end].isdigit():
        return True
    return False


def iter_figures(text: str, *, apply_ignores: bool = True) -> list[FigureSpan]:
    ignored = _ignored_ranges(text) if apply_ignores else []
    figures: list[FigureSpan] = []
    for match in _FIGURE.finditer(text):
        start, end = match.start(), match.end()
        if _is_embedded_in_longer_digit_run(text, start, end):
            continue
        if apply_ignores and _inside_range(start, end, ignored):
            continue
        if match.group("rupee") is not None:
            token = match.group("rupee")
            suffix_match = re.search(r"(L|lakh|Cr|crore)\s*$", token, re.IGNORECASE)
            if suffix_match:
                numeric = token[: suffix_match.start()].strip()
                value = parse_figure_value(numeric, suffix_match.group(1))
            else:
                value = parse_figure_value(token)
        elif match.group("pct") is not None:
            value = parse_figure_value(match.group("plain"))
        elif match.group("suffix") is not None:
            value = parse_figure_value(match.group("amount"), match.group("suffix"))
        else:
            token = match.group("number")
            value = parse_figure_value(token)
        figures.append(FigureSpan(start=start, end=end, text=text[start:end], value=value))
    return _drop_nested_figures(figures)


def _drop_nested_figures(figures: list[FigureSpan]) -> list[FigureSpan]:
    if not figures:
        return figures
    kept: list[FigureSpan] = []
    for candidate in figures:
        if any(
            other.start <= candidate.start
            and other.end >= candidate.end
            and (other.start, other.end) != (candidate.start, candidate.end)
            for other in figures
        ):
            continue
        kept.append(candidate)
    return sorted(kept, key=lambda item: item.start)


def collect_numeric_values(payload: Any) -> set[float]:
    values: set[float] = set()

    def walk(node: Any) -> None:
        if node is None or isinstance(node, bool):
            return
        if isinstance(node, (int, float)):
            values.add(float(node))
            return
        if isinstance(node, str):
            for figure in iter_figures(node, apply_ignores=False):
                values.add(figure.value)
            return
        if isinstance(node, dict):
            for item in node.values():
                walk(item)
            return
        if isinstance(node, (list, tuple)):
            for item in node:
                walk(item)

    walk(payload)
    return values
