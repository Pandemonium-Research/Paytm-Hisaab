"""Build the browser-safe event fixture used by the presenter remote."""

from __future__ import annotations

import json
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
SOURCE = REPO_ROOT / "data" / "demo" / "visible" / "rails_events.json"
TARGET = Path(__file__).resolve().parents[1] / "public" / "demo-events.json"
MERCHANT_ID = "MID_DEMO_SAHANA"


def include_event(event: dict[str, object]) -> bool:
    if event.get("merchant_id") != MERCHANT_ID:
        return False
    if event.get("type") == "lien_marked":
        return True
    return event.get("type") == "payment_declined" and str(event.get("ts", "")).startswith("2026-03-24T")


def main() -> None:
    source_events = json.loads(SOURCE.read_text(encoding="utf-8"))
    events = [event for event in source_events if include_event(event)]
    lien_count = sum(event["type"] == "lien_marked" for event in events)
    decline_count = sum(event["type"] == "payment_declined" for event in events)
    if lien_count != 1 or decline_count != 3:
        raise RuntimeError(f"Expected 1 lien and 3 declines, found {lien_count} lien and {decline_count} declines")
    TARGET.write_text(json.dumps({"events": events}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {TARGET.relative_to(REPO_ROOT)} with {lien_count} lien_marked and {decline_count} payment_declined events")


if __name__ == "__main__":
    main()
