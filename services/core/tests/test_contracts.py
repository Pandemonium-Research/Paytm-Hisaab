from __future__ import annotations

from datetime import datetime, timezone
from typing import get_args

import pytest
from pydantic import BaseModel, ValidationError

from app.schemas.api import ENDPOINT_MODELS, REQUEST_MODELS
from app.schemas.api.ledger_ops import AGENT_CONFIDENCE_CAP, LedgerProposalRequest
from app.schemas.common import ANSWER_TO_LABELS, AnswerChoice, PredictionLabel
from app.schemas.ledger import (
    ClaimAnsweredPayload,
    CreditObservedPayload,
    EntryKind,
    LedgerEntry,
    PAYLOAD_MODELS,
)
from app.schemas.roles import ENDPOINT_PERMISSIONS, ROLE_ENTRY_KINDS, Role
from sim.catalog import ANSWER_CHOICES, PREDICTION_LABELS


NOW = datetime(2026, 3, 24, 9, 30, tzinfo=timezone.utc)

PAYLOAD_EXAMPLES = {
    EntryKind.CREDIT_OBSERVED: {
        "amount": 4200,
        "channel": "UPI_POS",
        "counterparty_id": "P123",
    },
    EntryKind.BILL_LINKED: {"bill_id": "BDM1", "line_count": 2, "total": 4200},
    EntryKind.LABEL_PROPOSED: {
        "label": "taxable_supply",
        "source": "rule",
        "rule_id": "bill-v1",
        "confidence": 1.0,
        "reason": "POS bill is linked.",
        "evidence_refs": ["BDM1"],
        "memory_refs": [],
    },
    EntryKind.QUESTION_ASKED: {
        "question_id": "Q1",
        "text": "What was this payment for?",
        "language": "en",
        "expires_at": NOW,
    },
    EntryKind.CLAIM_ANSWERED: {
        "question_id": "Q1",
        "answer": "sale",
        "label": "taxable_supply",
        "raw_text": "It was a sale.",
        "language": "en",
    },
    EntryKind.CLAIM_ANNOTATED: {
        "label": "personal_transfer",
        "raw_text": "Correction: this was from family.",
        "language": "en",
    },
    EntryKind.LABEL_DISPUTED: {
        "disputed_label": "taxable_supply",
        "reason": "This was not a sale.",
    },
    EntryKind.CASE_OPENED: {"case_id": "C1", "case_type": "freeze", "trigger_ref": "E1"},
    EntryKind.PACK_BUILT: {
        "pack_id": "PK1",
        "pdf_sha256": "a" * 64,
        "tier_totals": {"1": {"amount": 4200, "count": 1}},
    },
    EntryKind.PACK_APPROVED: {"pack_id": "PK1", "note": "Checked."},
    EntryKind.PACK_REJECTED: {"pack_id": "PK1", "reason": "Wrong attachment."},
    EntryKind.PACK_SENT: {
        "pack_id": "PK1",
        "destination": "simulated-outbox",
        "delivery_ref": "D1",
    },
    EntryKind.ANCHOR_CREATED: {
        "anchor_id": "A1",
        "digest_sha256": "b" * 64,
        "simulated": True,
    },
}


def ledger_row(kind: EntryKind) -> dict:
    return {
        "seq": 1,
        "merchant_id": "MID_DEMO_SAHANA",
        "chain_index": 0,
        "kind": kind.value,
        "txn_id": "DM0000001" if kind is not EntryKind.ANCHOR_CREATED else None,
        "payload": PAYLOAD_EXAMPLES[kind],
        "actor_role": "rails",
        "actor_ref": "test",
        "sim_at": NOW,
        "recorded_at": NOW,
        "prev_hash": b"previous",
        "hash": b"hash",
    }


@pytest.mark.parametrize("kind", list(EntryKind))
def test_every_entry_kind_has_a_payload_and_round_trips(kind: EntryKind) -> None:
    assert kind in PAYLOAD_MODELS
    entry = LedgerEntry.model_validate(ledger_row(kind))
    assert LedgerEntry.model_validate_json(entry.model_dump_json()) == entry


def test_discriminated_ledger_union_rejects_a_payload_for_another_kind() -> None:
    row = ledger_row(EntryKind.CREDIT_OBSERVED)
    row["payload"] = PAYLOAD_EXAMPLES[EntryKind.BILL_LINKED]
    with pytest.raises(ValidationError):
        LedgerEntry.model_validate(row)


def test_role_entry_matrix_is_total_and_uses_only_known_kinds() -> None:
    assert set(ROLE_ENTRY_KINDS) == set(Role)
    assert set().union(*ROLE_ENTRY_KINDS.values()) <= set(EntryKind)


def test_every_endpoint_has_a_role_and_models() -> None:
    assert ENDPOINT_PERMISSIONS.keys() == ENDPOINT_MODELS.keys()
    assert all(roles for roles in ENDPOINT_PERMISSIONS.values())
    assert all(response is not None for _, response in ENDPOINT_MODELS.values())


def agent_proposal(confidence: float) -> dict:
    return {
        "merchant_id": "MID_DEMO_SAHANA",
        "txn_id": "DM0000001",
        "sim_at": NOW,
        "proposal": {
            "label": "taxable_supply",
            "source": "agent",
            "model": "sarvam-test",
            "prompt_version": "v1",
            "confidence": confidence,
            "reason": "The payment text suggests a sale.",
        },
    }


def test_agent_confidence_cap_is_inclusive() -> None:
    LedgerProposalRequest.model_validate(agent_proposal(AGENT_CONFIDENCE_CAP))
    with pytest.raises(ValidationError):
        LedgerProposalRequest.model_validate(agent_proposal(AGENT_CONFIDENCE_CAP + 0.01))


def nested_models(annotation: object) -> set[type[BaseModel]]:
    found: set[type[BaseModel]] = set()
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        found.add(annotation)
    for argument in get_args(annotation):
        found |= nested_models(argument)
    return found


def test_no_request_model_declares_recorded_at() -> None:
    pending = list(REQUEST_MODELS)
    seen: set[type[BaseModel]] = set()
    while pending:
        model = pending.pop()
        if model in seen:
            continue
        seen.add(model)
        assert "recorded_at" not in model.model_fields, model.__name__
        for field in model.model_fields.values():
            pending.extend(nested_models(field.annotation) - seen)


def test_label_and_answer_vocabularies_do_not_drift_from_simulator() -> None:
    assert tuple(label.value for label in PredictionLabel) == PREDICTION_LABELS
    assert tuple(answer.value for answer in AnswerChoice) == tuple(ANSWER_CHOICES)


def test_money_rejects_float_values() -> None:
    with pytest.raises(ValidationError):
        CreditObservedPayload(amount=4200.0, channel="UPI_POS", counterparty_id="P123")


def test_admin_may_append_the_anchor_job_entry() -> None:
    # Section 6 names an "anchor job" that section 14 gives no role. WF60 reaches it through
    # POST /anchors/run, which is admin only, so admin has to be able to append the entry.
    assert EntryKind.ANCHOR_CREATED in ROLE_ENTRY_KINDS[Role.ADMIN]
    appendable = set().union(*ROLE_ENTRY_KINDS.values())
    assert appendable == set(EntryKind), set(EntryKind) - appendable


def test_answer_to_label_mapping_does_not_drift_from_simulator() -> None:
    for answer, labels in ANSWER_TO_LABELS.items():
        if answer is AnswerChoice.NOT_SURE:
            # sim maps not_sure to no truth label at all; core records it as unclassified,
            # which is a prediction label and never a truth.
            assert labels == frozenset({PredictionLabel.UNCLASSIFIED})
            continue
        assert tuple(sorted(l.value for l in labels)) == tuple(
            sorted(ANSWER_CHOICES[answer.value])
        )


def test_claim_records_both_the_answer_and_the_label_it_implies() -> None:
    claim = ClaimAnsweredPayload(
        question_id="Q1",
        answer=AnswerChoice.FAMILY,
        label=PredictionLabel.PERSONAL_TRANSFER,
        raw_text="my sister sent it",
        language="kn",
    )
    assert claim.answer is AnswerChoice.FAMILY

    with pytest.raises(ValidationError):
        ClaimAnsweredPayload(
            question_id="Q1",
            answer=AnswerChoice.FAMILY,
            label=PredictionLabel.TAXABLE_SUPPLY,
            raw_text="my sister sent it",
            language="kn",
        )
