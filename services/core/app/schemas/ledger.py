"""Typed payloads and the append-only ledger envelope.

Hashes are deliberately not computed in this module. The hash input is the UTF-8 canonical JSON
of ``{merchant_id, chain_index, kind, txn_id, payload, actor_role, sim_at, recorded_at}``, followed
by the raw previous hash bytes, then SHA-256. Canonical JSON sorts object keys, uses no insignificant
whitespace, preserves array order, emits enum values, formats aware datetimes as ISO-8601, and
encodes no NaN or infinity. ``recorded_at`` is assigned by PostgreSQL ``clock_timestamp()``.
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, RootModel, model_validator

from .common import (
    ANSWER_TO_LABELS,
    AnswerChoice,
    CaseId,
    Confidence,
    ContractModel,
    EntrySequence,
    EvidenceTier,
    MerchantId,
    Money,
    PackId,
    PredictionLabel,
    QuestionId,
    TransactionId,
)


class EntryKind(str, Enum):
    CREDIT_OBSERVED = "credit.observed"
    BILL_LINKED = "bill.linked"
    LABEL_PROPOSED = "label.proposed"
    QUESTION_ASKED = "question.asked"
    CLAIM_ANSWERED = "claim.answered"
    CLAIM_ANNOTATED = "claim.annotated"
    LABEL_DISPUTED = "label.disputed"
    CASE_OPENED = "case.opened"
    PACK_BUILT = "pack.built"
    PACK_APPROVED = "pack.approved"
    PACK_REJECTED = "pack.rejected"
    PACK_SENT = "pack.sent"
    ANCHOR_CREATED = "anchor.created"


class ProposalSource(str, Enum):
    RULE = "rule"
    AGENT = "agent"


class CreditObservedPayload(ContractModel):
    amount: Money
    channel: str
    counterparty_id: str


class BillLinkedPayload(ContractModel):
    bill_id: str
    line_count: Annotated[int, Field(ge=1)]
    total: Money


class LabelProposedPayload(ContractModel):
    label: PredictionLabel
    source: ProposalSource
    rule_id: str | None = None
    model: str | None = None
    prompt_version: str | None = None
    confidence: Confidence
    reason: str
    evidence_refs: list[str] = Field(default_factory=list)
    memory_refs: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def source_metadata_matches(self) -> "LabelProposedPayload":
        if self.source is ProposalSource.RULE:
            if not self.rule_id or self.model is not None or self.prompt_version is not None:
                raise ValueError("a rule proposal needs rule_id and no model metadata")
        elif not self.model or not self.prompt_version or self.rule_id is not None:
            raise ValueError("an agent proposal needs model and prompt_version and no rule_id")
        return self


class QuestionAskedPayload(ContractModel):
    question_id: QuestionId
    text: str
    language: str
    expires_at: AwareDatetime


class ClaimAnsweredPayload(ContractModel):
    """What the merchant said, and what we took it to mean.

    Both are recorded. The ledger is a provenance record, so an answer of "sale" that we later
    read as ``taxable_supply`` has to stay distinguishable from the merchant having said
    ``taxable_supply``, which they never do: they tap one of seven words (section 2C.4).
    """

    question_id: QuestionId
    answer: AnswerChoice
    label: PredictionLabel
    raw_text: str | None = None
    media_sha256: str | None = None
    language: str

    @model_validator(mode="after")
    def has_answer_material(self) -> "ClaimAnsweredPayload":
        if (self.raw_text is None) == (self.media_sha256 is None):
            raise ValueError("supply exactly one of raw_text or media_sha256")
        return self

    @model_validator(mode="after")
    def label_follows_from_answer(self) -> "ClaimAnsweredPayload":
        allowed = ANSWER_TO_LABELS[self.answer]
        if self.label not in allowed:
            raise ValueError(
                f"answer {self.answer.value!r} cannot mean {self.label.value!r}; "
                f"expected one of {sorted(l.value for l in allowed)}"
            )
        return self


class ClaimAnnotatedPayload(ContractModel):
    label: PredictionLabel
    raw_text: str
    language: str


class LabelDisputedPayload(ContractModel):
    disputed_label: PredictionLabel
    reason: str


class CaseOpenedPayload(ContractModel):
    case_id: CaseId
    case_type: Literal["freeze", "notice"]
    trigger_ref: str


class TierTotal(ContractModel):
    amount: Money
    count: Annotated[int, Field(ge=0)]


class PackBuiltPayload(ContractModel):
    pack_id: PackId
    pdf_sha256: str
    tier_totals: dict[EvidenceTier, TierTotal]


class PackApprovedPayload(ContractModel):
    pack_id: PackId
    note: str | None = None


class PackRejectedPayload(ContractModel):
    pack_id: PackId
    reason: str


class PackSentPayload(ContractModel):
    pack_id: PackId
    destination: str
    delivery_ref: str


class AnchorCreatedPayload(ContractModel):
    anchor_id: str
    digest_sha256: str
    simulated: bool
    ots_receipt: str | None = None
    git_commit_url: str | None = None


class _LedgerEntryBase(ContractModel):
    seq: EntrySequence
    merchant_id: MerchantId
    chain_index: Annotated[int, Field(ge=0)]
    txn_id: TransactionId | None = None
    actor_role: str
    actor_ref: str
    sim_at: AwareDatetime
    recorded_at: AwareDatetime
    prev_hash: bytes
    hash: bytes


class CreditObservedEntry(_LedgerEntryBase):
    kind: Literal[EntryKind.CREDIT_OBSERVED]
    payload: CreditObservedPayload


class BillLinkedEntry(_LedgerEntryBase):
    kind: Literal[EntryKind.BILL_LINKED]
    payload: BillLinkedPayload


class LabelProposedEntry(_LedgerEntryBase):
    kind: Literal[EntryKind.LABEL_PROPOSED]
    payload: LabelProposedPayload


class QuestionAskedEntry(_LedgerEntryBase):
    kind: Literal[EntryKind.QUESTION_ASKED]
    payload: QuestionAskedPayload


class ClaimAnsweredEntry(_LedgerEntryBase):
    kind: Literal[EntryKind.CLAIM_ANSWERED]
    payload: ClaimAnsweredPayload


class ClaimAnnotatedEntry(_LedgerEntryBase):
    kind: Literal[EntryKind.CLAIM_ANNOTATED]
    payload: ClaimAnnotatedPayload


class LabelDisputedEntry(_LedgerEntryBase):
    kind: Literal[EntryKind.LABEL_DISPUTED]
    payload: LabelDisputedPayload


class CaseOpenedEntry(_LedgerEntryBase):
    kind: Literal[EntryKind.CASE_OPENED]
    payload: CaseOpenedPayload


class PackBuiltEntry(_LedgerEntryBase):
    kind: Literal[EntryKind.PACK_BUILT]
    payload: PackBuiltPayload


class PackApprovedEntry(_LedgerEntryBase):
    kind: Literal[EntryKind.PACK_APPROVED]
    payload: PackApprovedPayload


class PackRejectedEntry(_LedgerEntryBase):
    kind: Literal[EntryKind.PACK_REJECTED]
    payload: PackRejectedPayload


class PackSentEntry(_LedgerEntryBase):
    kind: Literal[EntryKind.PACK_SENT]
    payload: PackSentPayload


class AnchorCreatedEntry(_LedgerEntryBase):
    kind: Literal[EntryKind.ANCHOR_CREATED]
    payload: AnchorCreatedPayload


LedgerEntryVariant = Annotated[
    CreditObservedEntry
    | BillLinkedEntry
    | LabelProposedEntry
    | QuestionAskedEntry
    | ClaimAnsweredEntry
    | ClaimAnnotatedEntry
    | LabelDisputedEntry
    | CaseOpenedEntry
    | PackBuiltEntry
    | PackApprovedEntry
    | PackRejectedEntry
    | PackSentEntry
    | AnchorCreatedEntry,
    Field(discriminator="kind"),
]


class LedgerEntry(RootModel[LedgerEntryVariant]):
    """A ledger row whose payload is selected and validated by ``kind``."""


PAYLOAD_MODELS: dict[EntryKind, type[ContractModel]] = {
    EntryKind.CREDIT_OBSERVED: CreditObservedPayload,
    EntryKind.BILL_LINKED: BillLinkedPayload,
    EntryKind.LABEL_PROPOSED: LabelProposedPayload,
    EntryKind.QUESTION_ASKED: QuestionAskedPayload,
    EntryKind.CLAIM_ANSWERED: ClaimAnsweredPayload,
    EntryKind.CLAIM_ANNOTATED: ClaimAnnotatedPayload,
    EntryKind.LABEL_DISPUTED: LabelDisputedPayload,
    EntryKind.CASE_OPENED: CaseOpenedPayload,
    EntryKind.PACK_BUILT: PackBuiltPayload,
    EntryKind.PACK_APPROVED: PackApprovedPayload,
    EntryKind.PACK_REJECTED: PackRejectedPayload,
    EntryKind.PACK_SENT: PackSentPayload,
    EntryKind.ANCHOR_CREATED: AnchorCreatedPayload,
}

