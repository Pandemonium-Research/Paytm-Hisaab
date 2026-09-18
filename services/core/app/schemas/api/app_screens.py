"""Screen-shaped read models for the merchant and officer PWAs."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from ..common import (
    CaseId,
    ContractModel,
    EvidenceTier,
    MerchantId,
    Money,
    PackId,
    PredictionLabel,
    TransactionId,
)


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


REQUEST_MODELS: tuple[type[ContractModel], ...] = ()

