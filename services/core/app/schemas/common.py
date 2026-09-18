"""Shared scalar types and small response envelopes."""

from __future__ import annotations

from enum import Enum, IntEnum
from typing import Annotated, Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field


class ContractModel(BaseModel):
    """Base for strict wire contracts."""

    model_config = ConfigDict(extra="forbid", use_enum_values=False)


# TODO(1.3): The plan does not fix ID syntax; keep external and synthetic IDs opaque.
MerchantId = Annotated[str, Field(min_length=1)]
TransactionId = Annotated[str, Field(min_length=1)]
CounterpartyId = Annotated[str, Field(min_length=1)]
CaseId = Annotated[str, Field(min_length=1)]
PackId = Annotated[str, Field(min_length=1)]
QuestionId = Annotated[str, Field(min_length=1)]
EntrySequence = Annotated[int, Field(ge=1)]
Money = Annotated[
    int,
    Field(strict=True, ge=0, description="Whole rupees; never paise or a float."),
]
Confidence = Annotated[float, Field(ge=0.0, le=1.0)]


class PredictionLabel(str, Enum):
    TAXABLE_SUPPLY = "taxable_supply"
    EXEMPT_SUPPLY = "exempt_supply"
    PERSONAL_TRANSFER = "personal_transfer"
    INTER_ACCOUNT = "inter_account"
    NON_BUSINESS = "non_business"
    REFUND_REVERSAL = "refund_reversal"
    DUPLICATE = "duplicate"
    UNCLASSIFIED = "unclassified"


class AnswerChoice(str, Enum):
    SALE = "sale"
    FAMILY = "family"
    OWN_MONEY = "own_money"
    LOAN_OR_GIFT = "loan_or_gift"
    REFUND = "refund"
    DOUBLE_PAYMENT = "double_payment"
    NOT_SURE = "not_sure"


# Resolution choices for current_view, mirroring sim/catalog.py ANSWER_CHOICES. "sale" keeps the
# machine's supply class, while "not_sure" resolves to nothing and leaves the machine label.
ANSWER_TO_LABELS: dict["AnswerChoice", frozenset["PredictionLabel"]] = {}


class EvidenceTier(IntEnum):
    # Backed by a bill recorded before the case and consistent with a supply label.
    BILL = 1
    # Derived before the case by a rule, or from the payment's own data, with no claim.
    RULE = 2
    # The merchant's pre-case answer, including an inherited answer about the same payer.
    ANSWER = 3
    # An annotation, or anything recorded after the case opened.
    AFTER_NOTICE = 4


class Pagination(ContractModel):
    # TODO(1.3): Confirm the default and maximum page sizes when routes are implemented.
    limit: Annotated[
        int, Field(ge=1, le=200, description="Maximum number of items to return.")
    ] = 50
    cursor: Annotated[
        str | None, Field(description="Opaque cursor from the previous page.")
    ] = None


T = TypeVar("T")


class Page(ContractModel, Generic[T]):
    items: list[T]
    next_cursor: str | None = None


class ErrorDetail(ContractModel):
    code: str
    message: str
    field: str | None = None


class ErrorEnvelope(ContractModel):
    error: ErrorDetail


class AcceptedResponse(ContractModel):
    accepted: bool = True
    id: str | None = None


ANSWER_TO_LABELS.update(
    {
        AnswerChoice.SALE: frozenset(
            {PredictionLabel.TAXABLE_SUPPLY, PredictionLabel.EXEMPT_SUPPLY}
        ),
        AnswerChoice.FAMILY: frozenset({PredictionLabel.PERSONAL_TRANSFER}),
        AnswerChoice.OWN_MONEY: frozenset({PredictionLabel.INTER_ACCOUNT}),
        AnswerChoice.LOAN_OR_GIFT: frozenset({PredictionLabel.NON_BUSINESS}),
        AnswerChoice.REFUND: frozenset({PredictionLabel.REFUND_REVERSAL}),
        AnswerChoice.DOUBLE_PAYMENT: frozenset({PredictionLabel.DUPLICATE}),
        AnswerChoice.NOT_SURE: frozenset(),
    }
)
