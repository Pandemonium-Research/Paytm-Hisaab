"""Screen-shaped read models for the merchant and officer PWAs."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, model_validator

from ..common import (
    AnswerChoice,
    CaseId,
    ContractModel,
    EvidenceTier,
    MerchantId,
    Money,
    PackId,
    Pagination,
    PredictionLabel,
    QuestionId,
    TransactionId,
)


M2_ANSWER_CHOICES = frozenset(
    {
        AnswerChoice.SALE,
        AnswerChoice.FAMILY,
        AnswerChoice.OWN_MONEY,
        AnswerChoice.LOAN_OR_GIFT,
        AnswerChoice.NOT_SURE,
    }
)


class MerchantAppQuery(ContractModel):
    merchant: Annotated[
        MerchantId, Field(description="Merchant whose app screen to return.")
    ]


class AppPaymentsQuery(Pagination):
    merchant: Annotated[
        MerchantId, Field(description="Merchant whose payments to return.")
    ]


class DisplayAmount(ContractModel):
    amount: Money
    amount_text: str


class HomeAlert(ContractModel):
    kind: Literal["question", "threshold", "case", "notice"]
    title: str
    body: str
    href: str


class AppHomeResponse(ContractModel):
    merchant_id: MerchantId
    business_name: str
    as_of: AwareDatetime
    balance: DisplayAmount
    today_received: DisplayAmount
    questions_due: Annotated[int, Field(ge=0)]
    open_cases: Annotated[int, Field(ge=0)]
    alerts: list[HomeAlert]


class QuestionAnswerChip(ContractModel):
    answer: AnswerChoice
    text: str


class AppQuestionCard(ContractModel):
    question_id: QuestionId
    txn_id: TransactionId
    amount: Money
    amount_text: str
    ts: AwareDatetime
    payer_name: str
    channel: str
    question: str
    language: str
    answer_chips: Annotated[list[QuestionAnswerChip], Field(min_length=5, max_length=5)]
    position: Annotated[int, Field(ge=1)]
    total: Annotated[int, Field(ge=1)]

    @model_validator(mode="after")
    def uses_the_m2_answer_subset(self) -> "AppQuestionCard":
        answers = [chip.answer for chip in self.answer_chips]
        if len(set(answers)) != len(answers):
            raise ValueError("M2 answer chips must be distinct")
        if frozenset(answers) != M2_ANSWER_CHOICES:
            raise ValueError("M2 answer chips must use the five contracted AnswerChoice values")
        if self.position > self.total:
            raise ValueError("question position cannot exceed total")
        return self


class AppQuestionsResponse(ContractModel):
    items: list[AppQuestionCard]
    automatically_settled_count: Annotated[int, Field(ge=0)]
    closing_text: str


class AppConversationMessage(ContractModel):
    message_id: str
    direction: Literal["in", "out"]
    text: str
    content_type: str
    language: str | None
    sim_at: AwareDatetime


class AppConversationResponse(ContractModel):
    items: list[AppConversationMessage]


class PaymentRow(ContractModel):
    txn_id: TransactionId
    ts: AwareDatetime
    counterparty_name: str
    amount: Money
    amount_text: str
    channel: str
    effective_label: PredictionLabel | None
    needs_answer: bool


class AppPaymentsResponse(ContractModel):
    items: list[PaymentRow]
    next_cursor: str | None = None


class EvidenceBadge(ContractModel):
    tier: EvidenceTier
    title: str
    detail: str


class AppPaymentDetailResponse(PaymentRow):
    utr: str
    note: str
    machine_label: PredictionLabel | None
    claim_label: PredictionLabel | None
    conflict: bool
    evidence: list[EvidenceBadge]


class MerchantCaseRow(ContractModel):
    case_id: CaseId
    case_type: Literal["freeze", "notice"]
    status: str
    opened_at: AwareDatetime
    title: str
    disputed_amount: Money | None = None
    disputed_amount_text: str | None = None


class AppCasesResponse(ContractModel):
    items: list[MerchantCaseRow]


class TurnoverBand(ContractModel):
    label: str
    amount: Money
    amount_text: str


class AppTurnoverResponse(ContractModel):
    period: str
    aggregate: Money
    aggregate_text: str
    threshold: Money
    threshold_text: str
    bands: list[TurnoverBand]
    crossed_on: date | None
    projected_crossing_on: date | None
    registration_required: bool
    explanation: str


class OfficerQueueRow(ContractModel):
    case_id: CaseId
    merchant_id: MerchantId
    business_name: str
    case_type: Literal["freeze", "notice"]
    opened_at: AwareDatetime
    disputed_amount: Money | None = None
    disputed_amount_text: str | None = None
    weak_evidence_share: Annotated[float, Field(ge=0, le=1)]
    escalation_reasons: list[str]


class OfficerQueueResponse(ContractModel):
    items: list[OfficerQueueRow]


class OfficerCaseResponse(ContractModel):
    case: OfficerQueueRow
    pack_id: PackId | None
    status: str
    timeline: list[str]
    tier_totals: list[TurnoverBand]
    chain_ok: bool
    pdf_url: str | None


class OfficerOutboxRow(ContractModel):
    pack_id: PackId
    case_id: CaseId
    merchant_id: MerchantId
    business_name: str
    destination: str
    delivery_ref: str
    status: str
    outcome: str | None = None
    simulated: bool
    freeze_at: AwareDatetime
    pack_built_at: AwareDatetime
    approved_at: AwareDatetime
    sent_at: AwareDatetime
    freeze_to_pack_seconds: Annotated[int, Field(ge=0)]
    pack_to_approval_seconds: Annotated[int, Field(ge=0)]
    usable_balance: DisplayAmount


class OfficerOutboxResponse(ContractModel):
    items: list[OfficerOutboxRow]


REQUEST_MODELS: tuple[type[ContractModel], ...] = ()
