"""Executable role policy from IMPLEMENTATION_PLAN.md section 14."""

from __future__ import annotations

from enum import Enum

from .ledger import EntryKind


class Role(str, Enum):
    RAILS = "rails"
    PROVENANCE = "provenance"
    CONVERSATION = "conversation"
    EVIDENCE = "evidence"
    OFFICER = "officer"
    ADMIN = "admin"
    APP = "app"


ROLE_ENTRY_KINDS: dict[Role, frozenset[EntryKind]] = {
    Role.RAILS: frozenset(
        {EntryKind.CREDIT_OBSERVED, EntryKind.BILL_LINKED, EntryKind.CASE_OPENED}
    ),
    Role.PROVENANCE: frozenset({EntryKind.LABEL_PROPOSED}),
    Role.CONVERSATION: frozenset(
        {
            EntryKind.QUESTION_ASKED,
            EntryKind.CLAIM_ANSWERED,
            EntryKind.CLAIM_ANNOTATED,
            EntryKind.LABEL_DISPUTED,
        }
    ),
    Role.EVIDENCE: frozenset({EntryKind.CASE_OPENED, EntryKind.PACK_BUILT}),
    Role.OFFICER: frozenset(
        {EntryKind.PACK_APPROVED, EntryKind.PACK_REJECTED, EntryKind.PACK_SENT}
    ),
    # Section 6 calls the anchor writer an "anchor job" and section 14 declares no role for it.
    # The job is WF60 calling POST /anchors/run, which section 7 restricts to admin, so admin is
    # the only role that can be holding the key when anchor.created is appended.
    Role.ADMIN: frozenset({EntryKind.ANCHOR_CREATED}),
    # The credential is shipped in the merchant browser and must never append ledger evidence.
    Role.APP: frozenset(),
}


ALL_ROLES = frozenset(Role)
# The app key ships in a browser; guards are server-side and prompts must not be exposed there.
NON_APP_ROLES = ALL_ROLES - {Role.APP}
AGENT_READ_ROLES = frozenset({Role.PROVENANCE, Role.CONVERSATION, Role.EVIDENCE})
OFFICER_ADMIN = frozenset({Role.OFFICER, Role.ADMIN})

# Each concrete section 7 route is a key exactly once. Dynamic paths use FastAPI notation.
ENDPOINT_PERMISSIONS: dict[str, frozenset[Role]] = {
    "POST /rails/credits": frozenset({Role.RAILS}),
    "POST /rails/debits": frozenset({Role.RAILS}),
    "POST /rails/bills": frozenset({Role.RAILS}),
    "POST /rails/events": frozenset({Role.RAILS}),
    "GET /merchants/{id}": AGENT_READ_ROLES,
    "GET /credits": AGENT_READ_ROLES,
    "GET /credits/{txn}": AGENT_READ_ROLES,
    "GET /credits/by-utr/{utr}": AGENT_READ_ROLES,
    "GET /payers/{cp}/history": AGENT_READ_ROLES,
    "POST /skills/classify-rules": frozenset({Role.PROVENANCE}),
    "POST /ledger/proposals": frozenset({Role.PROVENANCE}),
    "POST /skills/select-questions": frozenset({Role.PROVENANCE}),
    "POST /ledger/questions": frozenset({Role.CONVERSATION}),
    "POST /ledger/claims": frozenset({Role.CONVERSATION}),
    "POST /skills/turnover": frozenset({Role.EVIDENCE}),
    "POST /skills/threshold": frozenset({Role.EVIDENCE}),
    "POST /skills/isolate": frozenset({Role.EVIDENCE}),
    "POST /skills/tiers": frozenset({Role.EVIDENCE}),
    "POST /skills/escalation-check": frozenset({Role.EVIDENCE}),
    "POST /cases": frozenset({Role.EVIDENCE}),
    "POST /packs": frozenset({Role.EVIDENCE}),
    "POST /guards/numbers": NON_APP_ROLES,
    "POST /guards/citations": NON_APP_ROLES,
    "POST /guards/no-innocence": NON_APP_ROLES,
    "POST /guards/extraction": NON_APP_ROLES,
    "POST /guards/language": NON_APP_ROLES,
    "POST /packs/{id}/approve": frozenset({Role.OFFICER}),
    "POST /packs/{id}/reject": frozenset({Role.OFFICER}),
    "POST /outbox/{pack}/send": frozenset({Role.OFFICER}),
    "GET /ledger/verify": OFFICER_ADMIN,
    "GET /ledger/{m}/entries": OFFICER_ADMIN,
    "GET /anchors": OFFICER_ADMIN,
    "POST /sim/clock": frozenset({Role.ADMIN}),
    "POST /sim/replay": frozenset({Role.ADMIN}),
    "POST /sim/reset": frozenset({Role.ADMIN}),
    "POST /sim/tamper": frozenset({Role.ADMIN}),
    "POST /anchors/run": frozenset({Role.ADMIN}),
    "POST /assistant/inbound": frozenset({Role.APP}),
    "GET /assistant/stream": frozenset({Role.APP}),
    "POST /assistant/outbound": frozenset({Role.CONVERSATION}),
    "GET /app/home": frozenset({Role.APP}),
    "GET /app/questions": frozenset({Role.APP}),
    "GET /app/payments": frozenset({Role.APP}),
    "GET /app/payments/{txn}": frozenset({Role.APP}),
    "GET /app/cases": frozenset({Role.APP}),
    "GET /app/turnover": frozenset({Role.APP}),
    "PUT /app/profile": frozenset({Role.APP}),
    "GET /app/officer/queue": frozenset({Role.OFFICER}),
    "GET /app/officer/cases/{id}": frozenset({Role.OFFICER}),
    "GET /app/officer/outbox": frozenset({Role.OFFICER}),
    "POST /app/push/subscribe": frozenset({Role.APP, Role.OFFICER}),
    "GET /prompts/{name}": NON_APP_ROLES,
    # Phase 1 names /config, although section 7 omits it.
    "GET /config": ALL_ROLES,
}
