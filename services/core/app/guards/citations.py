"""6.6 citations guard: only verified ``cite_as`` strings from ``legal/citations.yaml`` may appear."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

from ..schemas.api.guards import GuardResponse, OffendingSpan
from .paths import default_citations_path, repo_root


def _load_entries(path: Path) -> list[dict[str, Any]]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("citations file must be a mapping")
    citations = data.get("citations")
    if not isinstance(citations, list) or not citations:
        raise ValueError("citations file is missing a citations list")
    entries: list[dict[str, Any]] = []
    for item in citations:
        if not isinstance(item, dict):
            raise ValueError("each citation must be a mapping")
        entry = dict(item)
        entry.setdefault("verified", False)
        entries.append(entry)
    return entries

_CITATION_HINT = re.compile(
    r"""
    (?:Section\s+\d+[\w()\s,./-]{0,120}?\d{4})
    |(?:Notification\s+No\.\s*[\w./-]+[^\n]{0,120})
    |(?:[\w\s.]+\sv\.\s[\w\s.,]+(?:Writ|Petition|Civil)[^\n]{0,160})
    |(?:Standard Operating Procedure[^\n]{0,160})
    |(?:PIB,\s*Ministry[^\n]{0,160})
    """,
    re.IGNORECASE | re.VERBOSE,
)


def _resolve_citations_path(context: dict[str, Any]) -> Path:
    raw = context.get("citations_path")
    if raw:
        return (repo_root() / str(raw)).resolve()
    return default_citations_path()


def _distinctive_tokens(cite_as: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9]{4,}", cite_as)]


def _resembles(haystack: str, cite_as: str) -> bool:
    if cite_as in haystack:
        return False
    tokens = _distinctive_tokens(cite_as)
    if len(tokens) < 4:
        return False
    lower = haystack.lower()
    hits = sum(1 for token in tokens if token in lower)
    return hits / len(tokens) >= 0.55


def _resembles_span(text: str, cite_as: str) -> tuple[int, int]:
    tokens = _distinctive_tokens(cite_as)
    lower = text.lower()
    positions: list[tuple[int, int]] = []
    for token in tokens:
        idx = lower.find(token)
        if idx == -1:
            continue
        positions.append((idx, idx + len(token)))
    if not positions:
        return 0, len(text)
    start = min(left for left, _ in positions)
    end = max(right for _, right in positions)
    return start, end


def _range_covered(start: int, end: int, ranges: list[tuple[int, int]]) -> bool:
    return any(left <= start and right >= end for left, right in ranges)


def _merge_ranges(ranges: list[tuple[int, int]]) -> list[tuple[int, int]]:
    if not ranges:
        return ranges
    ordered = sorted(ranges)
    merged = [ordered[0]]
    for start, end in ordered[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged


def check_citations(text: str, context: dict[str, Any]) -> GuardResponse:
    try:
        path = _resolve_citations_path(context)
        entries = _load_entries(path)
    except Exception as exc:
        return GuardResponse(
            guard="citations",
            passed=False,
            offending_spans=[
                OffendingSpan(
                    start=0,
                    end=len(text),
                    text=text,
                    reason=f"Could not load citations allowlist: {exc}",
                )
            ],
        )

    spans: list[OffendingSpan] = []
    allowed_ranges: list[tuple[int, int]] = []

    for entry in sorted(entries, key=lambda item: len(str(item.get("cite_as", ""))), reverse=True):
        cite_as = str(entry.get("cite_as") or "")
        citation_id = str(entry.get("id") or "unknown")
        if not cite_as:
            continue
        start = 0
        while True:
            idx = text.find(cite_as, start)
            if idx == -1:
                break
            end = idx + len(cite_as)
            if entry.get("verified"):
                allowed_ranges.append((idx, end))
            else:
                spans.append(
                    OffendingSpan(
                        start=idx,
                        end=end,
                        text=text[idx:end],
                        reason=f"Citation {citation_id!r} is unverified and blocks approval.",
                    )
                )
            start = end

    allowed_ranges = _merge_ranges(allowed_ranges)

    for entry in entries:
        cite_as = str(entry.get("cite_as") or "")
        citation_id = str(entry.get("id") or "unknown")
        if not cite_as or cite_as in text:
            continue
        if not _resembles(text, cite_as):
            continue
        start, end = _resembles_span(text, cite_as)
        if _range_covered(start, end, allowed_ranges):
            continue
        spans.append(
            OffendingSpan(
                start=start,
                end=end,
                text=text[start:end],
                reason=f"Citation was reworded; it resembles {citation_id!r} but must use cite_as verbatim.",
            )
        )

    for match in _CITATION_HINT.finditer(text):
        start, end = match.start(), match.end()
        if _range_covered(start, end, allowed_ranges):
            continue
        snippet = text[start:end]
        if any(str(entry.get("cite_as") or "") in snippet for entry in entries):
            continue
        resembles_id = None
        for entry in entries:
            cite_as = str(entry.get("cite_as") or "")
            if cite_as and _resembles(snippet, cite_as):
                resembles_id = str(entry.get("id") or "unknown")
                break
        if resembles_id:
            spans.append(
                OffendingSpan(
                    start=start,
                    end=end,
                    text=snippet,
                    reason=(
                        f"Citation was reworded; it resembles {resembles_id!r} but must use cite_as verbatim."
                    ),
                )
            )
            continue
        spans.append(
            OffendingSpan(
                start=start,
                end=end,
                text=snippet,
                reason="Citation is not on the allowlist.",
            )
        )

    return GuardResponse(guard="citations", passed=not spans, offending_spans=spans)
