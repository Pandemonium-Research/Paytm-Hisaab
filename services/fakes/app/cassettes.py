"""Record and replay for the provider fakes (task 2F.2, plan section 16a).

A live window is the only time this project spends credits, so every real response is paid for
once and then reused for the rest of the build. Recording writes a cassette per request;
afterwards the fakes replay exact matches and fall back to their deterministic rules.

The format is frozen in `services/core/app/schemas/cassette.py` (task 1.3). This module is the
only implementation of the request key, so the recorder and the replayer cannot disagree: they
are the same code path, running in the same process, differing only in `HISAAB_RECORD`.

**Headers are an allowlist, not a denylist.** The frozen format says normalisation removes
authorisation, cookies, trace and correlation IDs, signatures, nonces and multipart boundaries.
Listing what to drop means a header nobody thought of silently changes the key and a cassette
stops matching, which is only discovered when a paid recording turns out to be unusable. Keeping
only the headers that can change a provider's answer gives the same result and cannot rot.

**Media bytes are deliberately not recorded.** A Twilio media URL carries SIDs that Twilio
generates at record time and the fakes generate at replay time, so such a cassette could never
match. The fakes synthesise media deterministically already (task 2F.6). What cannot be
synthesised, and so is worth paying for, is real speech, real audio and real Vision output, all
of which are Sarvam calls keyed on their own request bodies.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Only these can change what a provider answers. Everything else is dropped before hashing.
# `accept` is deliberately absent: it varies by client (n8n, curl, a test client all differ),
# so including it means a cassette recorded through one never replays for another.
SIGNIFICANT_HEADERS = frozenset({"content-type"})

# Twilio account SIDs sit in the path and differ between the real account and the fakes.
_ACCOUNT_SID = re.compile(r"/AC[0-9a-fA-F]{32}(?=/|$)")

CASSETTE_ROOT = Path(__file__).resolve().parent.parent / "cassettes"
SCHEMA_VERSION = 1


def _canonical(value: Any) -> str:
    """Canonical JSON: sorted keys, no insignificant whitespace, array order preserved."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _normalise_headers(headers: dict[str, str]) -> dict[str, str]:
    kept = {}
    for name, value in headers.items():
        lowered = name.lower()
        if lowered not in SIGNIFICANT_HEADERS:
            continue
        if lowered == "content-type":
            # Drop the generated multipart boundary and any charset noise.
            value = value.split(";", 1)[0].strip().lower()
        kept[lowered] = value
    return dict(sorted(kept.items()))


def _normalise_query(query: dict[str, Any]) -> dict[str, Any]:
    # Cache-busting parameters exist only to defeat caches, so they cannot affect the answer.
    dropped = {"_", "cb", "cachebuster", "ts", "timestamp", "nonce"}
    return {k: query[k] for k in sorted(query) if k.lower() not in dropped}


def normalise(
    *,
    method: str,
    path: str,
    query: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    body: Any = None,
) -> dict[str, Any]:
    """The request as it is hashed and stored, with volatile transport detail removed."""
    return {
        "method": method.upper(),
        "path": _ACCOUNT_SID.sub("/{AccountSid}", path),
        "query": _normalise_query(query or {}),
        "headers": _normalise_headers(headers or {}),
        "body": body,
    }


def request_key(normalised: dict[str, Any]) -> str:
    """Lowercase SHA-256 hex digest of the canonical normalised request."""
    return hashlib.sha256(_canonical(normalised).encode("utf-8")).hexdigest()


def _path_for(provider: str, key: str) -> Path:
    return CASSETTE_ROOT / provider / f"{key}.json"


def replay(provider: str, normalised: dict[str, Any]) -> dict[str, Any] | None:
    """The recorded response for this request, or None to fall through to the rules."""
    path = _path_for(provider, request_key(normalised))
    if not path.is_file():
        return None
    cassette = json.loads(path.read_text(encoding="utf-8"))
    return cassette.get("response")


def save(
    *,
    provider: str,
    endpoint: str,
    normalised: dict[str, Any],
    status: int,
    headers: dict[str, str],
    body: Any,
    live_window: str,
) -> Path:
    key = request_key(normalised)
    cassette = {
        "schema_version": SCHEMA_VERSION,
        "provider": provider,
        "endpoint": endpoint,
        "request_key": key,
        "normalised_request": normalised,
        "response": {
            "status": status,
            "headers": _normalise_headers(headers),
            "body": body,
        },
        "live_window": live_window,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    path = _path_for(provider, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(cassette, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def recording() -> bool:
    """Recording needs both switches. HISAAB_RECORD alone must never reach a paid provider."""
    return os.environ.get("HISAAB_RECORD") == "1" and os.environ.get("HISAAB_LIVE") == "1"


def record_guard() -> None:
    """Refuse loudly rather than record nothing, which is the expensive failure."""
    if os.environ.get("HISAAB_RECORD") == "1" and os.environ.get("HISAAB_LIVE") != "1":
        raise RuntimeError(
            "HISAAB_RECORD=1 needs HISAAB_LIVE=1. Recording without live mode would write "
            "cassettes of the fakes' own answers, which is worse than not recording: the L1 "
            "budget would be spent and the cassettes would be worthless. "
            "Use `python tasks.py --live --record up`."
        )


def live_window() -> str:
    return os.environ.get("HISAAB_LIVE_WINDOW", "L1")


def forward(
    *,
    upstream: str,
    method: str,
    path: str,
    query: dict[str, Any],
    headers: dict[str, str],
    raw_body: bytes,
    timeout: float = 60.0,
) -> tuple[int, dict[str, str], bytes]:
    """Send the request to the real provider. Only ever called when `recording()` is true."""
    if not recording():
        raise RuntimeError("forward() called outside record mode")
    url = upstream.rstrip("/") + path
    if query:
        url += "?" + urllib.parse.urlencode(query, doseq=True)
    request = urllib.request.Request(url, data=raw_body or None, method=method.upper())
    for name, value in headers.items():
        request.add_header(name, value)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        # A provider error is worth recording: it is what the real service said, and paying to
        # discover it twice helps nobody.
        return error.code, dict(error.headers), error.read()
