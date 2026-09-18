"""Deterministic skill request and response contracts."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from ..common import (
    CaseId,
    Confidence,
    ContractModel,
    EvidenceTier,
    MerchantId,
    Money,
    PredictionLabel,
    TransactionId,
)
from .reads import GeoPoint


# Question-budget policy. Names keep later config extraction mechanical.
QUESTION_LOW_CONFIDENCE = 0.75
QUESTION_NON_SALE_MIN_RUPEES = 10_000
QUESTION_NEW_PAYER_SALE_MIN_RUPEES = 3_000
QUESTION_NEW_PAYER_MAX_PRIOR_CREDITS = 3
QUESTION_ABSOLUTE_MIN_RUPEES = 500
QUESTION_THRESHOLD_PROXIMITY_FRACTION = 0.15
QUESTION_THRESHOLD_PROXIMITY_MULTIPLIER = 1.5
QUESTION_DAILY_LIMIT = 3
QUESTION_EXPIRY_DAYS = 7
# The two orderings in section 7 act at different stages: priority picks which candidates make
# the day's three, then those three are asked least confident first. Neither overrides the other.

# TODO(1.3): Verify the provisional legal and operational thresholds in plan section 22.
ESCALATION_SMALL_SUM_LIMIT_RUPEES = 50_000
ESCALATION_WEAK_TIERS = frozenset({EvidenceTier.ANSWER, EvidenceTier.AFTER_NOTICE})
ESCALATION_WEAK_SHARE = 0.40
ESCALATION_REPEAT_FREEZE_DAYS = 90


class ClassifyCredit(ContractModel):
    txn_id: TransactionId
    amount: Money
    channel: str
    counterparty_id: str
    counterparty_name: str
    note: str = ""
    has_bill: bool
    prior_credit_count: Annotated[int, Field(ge=0)]
    merchant_has_paid_them: bool
    own_account_cue: bool
    surname_cue: bool
    payer_fact: PredictionLabel | None = None


class ClassifyRulesRequest(ContractModel):
    merchant_id: MerchantId
    as_of: AwareDatetime
    credits: list[ClassifyCredit]


class RuleClassification(ContractModel):
    txn_id: TransactionId
    label: PredictionLabel
    confidence: Confidence
    rule_id: str
    ask: bool
    reason: str


class ClassifyResult(ContractModel):
    txn_id: TransactionId
    result: RuleClassification | None


class ClassifyRulesResponse(ContractModel):
    results: list[ClassifyResult]


class QuestionCandidate(ContractModel):
    txn_id: TransactionId
    payer_id: str
    amount: Money
    label: PredictionLabel | None
    confidence: Confidence
    strictly_prior_credit_count: Annotated[int, Field(ge=0)]
    has_bill: bool
    payer_fact_known: bool
    proposed_at: AwareDatetime


class SelectQuestionsRequest(ContractModel):
    merchant_id: MerchantId
    as_of: AwareDatetime
    candidates: list[QuestionCandidate]
    projected_turnover: Money
    threshold: Money
    already_asked_today: Annotated[int, Field(ge=0)] = 0


class SelectedQuestion(ContractModel):
    txn_id: TransactionId
    payer_id: str
    priority: Annotated[float, Field(ge=0)]
    expires_at: AwareDatetime


class SelectQuestionsResponse(ContractModel):
    selected: Annotated[list[SelectedQuestion], Field(max_length=QUESTION_DAILY_LIMIT)]
    expired_txn_ids: list[TransactionId]
    remaining_daily_budget: Annotated[int, Field(ge=0, le=QUESTION_DAILY_LIMIT)]


class DateRangeRequest(ContractModel):
    merchant_id: MerchantId
    period_from: date
    period_to: date
    as_of: AwareDatetime


class TurnoverRequest(DateRangeRequest):
    pass


class ExcludedTransaction(ContractModel):
    txn_id: TransactionId
    amount: Money
    label: PredictionLabel
    reason: str


class TurnoverWorking(ContractModel):
    description: str
    amount: Money
    estimated: bool


class TurnoverResponse(ContractModel):
    merchant_id: MerchantId
    taxable: Money
    exempt: Money
    aggregate: Money
    estimated_unbilled_taxable: Money
    estimated_unbilled_exempt: Money
    excluded: list[ExcludedTransaction]
    coverage_fraction: Annotated[float, Field(ge=0, le=1)]
    workings: list[TurnoverWorking]


class ThresholdRequest(DateRangeRequest):
    supply_kind: Literal["goods", "services"]
    gst_status: str
    aggregate_turnover: Money
    exclusively_exempt: bool


class ThresholdResponse(ContractModel):
    threshold: Money
    registration_required: bool
    reason: str
    crossed_on: date | None = None
    projected_crossing_on: date | None = None
    trailing_60_day_run_rate: Money | None = None
    warning_days: int | None = None


class IsolateRequest(ContractModel):
    merchant_id: MerchantId
    case_id: CaseId
    disputed_utr: str | None = None
    disputed_amount: Money
    disputed_date: date
    # TODO(1.3): The plan requires a date window but does not set its width.
    date_window_days: Annotated[int, Field(ge=0, le=30)] = 1
    as_of: AwareDatetime


class IsolationCandidate(ContractModel):
    txn_id: TransactionId
    utr: str
    amount: Money
    ts: AwareDatetime
    counterparty_name: str


class BillEvidence(ContractModel):
    bill_id: str
    line_items: list[str]
    total: Money


class DeviceEvidence(ContractModel):
    terminal_id: str
    device_id: str
    geo: GeoPoint


class IsolateResponse(ContractModel):
    matched: IsolationCandidate | None
    found_by: list[Literal["utr", "amount_date"]]
    same_amount_candidates: list[IsolationCandidate]
    bill: BillEvidence | None
    device: DeviceEvidence | None
    seven_day_credit_count: Annotated[int, Field(ge=0)]


class TiersRequest(DateRangeRequest):
    case_id: CaseId
    opened_at: AwareDatetime


class TierAggregate(ContractModel):
    tier: EvidenceTier
    amount: Money
    count: Annotated[int, Field(ge=0)]


class TiersResponse(ContractModel):
    totals: list[TierAggregate]
    strong_shape_fraction: Annotated[float, Field(ge=0, le=1)]


class EscalationCheckRequest(ContractModel):
    case_id: CaseId
    disputed_amount: Money
    disputed_tier: EvidenceTier
    effective_label: PredictionLabel
    claim_conflicts_with_bill: bool
    merchant_disputed_label: bool
    tier_3_4_share: Annotated[float, Field(ge=0, le=1)]
    prior_freeze_days_ago: Annotated[int, Field(ge=0)] | None = None


class EscalationCheckResponse(ContractModel):
    escalate: bool
    reasons: list[str]


REQUEST_MODELS = (
    ClassifyRulesRequest,
    SelectQuestionsRequest,
    TurnoverRequest,
    ThresholdRequest,
    IsolateRequest,
    TiersRequest,
    EscalationCheckRequest,
)
