"""General merchant, credit and payer-history read models."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, model_validator

from ..common import (
    ContractModel,
    CounterpartyId,
    EvidenceTier,
    MerchantId,
    Money,
    Pagination,
    PredictionLabel,
    TransactionId,
)
from .rails import RailChannel, RailCreditTransaction


class CreditsQuery(Pagination):
    merchant: Annotated[
        MerchantId, Field(description="Merchant whose credits to return.")
    ]
    as_of: Annotated[
        AwareDatetime | None,
        Field(description="Snapshot cutoff; when omitted, uses now on the sim clock."),
    ] = None
    # A caller that wants one day's credits should say so here rather than page the whole
    # history and discard it. Both bounds carry an offset on purpose: the chain stores UTC
    # and the screens speak IST, so a bare date would have to guess which one was meant.
    from_: Annotated[
        AwareDatetime | None,
        Field(
            alias="from",
            description=(
                "Inclusive start of the credit window, with a UTC offset; "
                "when omitted, starts at the merchant's first credit."
            ),
        ),
    ] = None
    to: Annotated[
        AwareDatetime | None,
        Field(
            description=(
                "Exclusive end of the credit window, with a UTC offset; a credit exactly "
                "at to is not returned; when omitted, ends at as_of."
            )
        ),
    ] = None

    @model_validator(mode="after")
    def window_must_hold_something(self) -> "CreditsQuery":
        if self.from_ is not None and self.to is not None and self.from_ >= self.to:
            raise ValueError("The credit window must be [from, to) with from before to.")
        return self


class PayerHistoryQuery(ContractModel):
    merchant: Annotated[
        MerchantId, Field(description="Merchant whose payer history to return.")
    ]
    as_of: Annotated[
        AwareDatetime | None,
        Field(
            description=(
                "Exclusive history cutoff; a credit exactly at as_of is not counted; "
                "when omitted, uses now on the sim clock."
            )
        ),
    ] = None


class GeoPoint(ContractModel):
    lat: Annotated[float, Field(ge=-90, le=90)]
    lon: Annotated[float, Field(ge=-180, le=180)]


class MerchantResponse(ContractModel):
    merchant_id: MerchantId
    business_name: str
    owner_name: str
    mcc: str
    category: str
    supply_kind: Literal["goods", "services"]
    gst_status: str
    gstin: str | None
    locality: str
    city: str
    state: str
    pincode: str
    geo: GeoPoint
    preferred_language: str
    terminals: list[str]
    linked_own_accounts: list[str]
    settlement_account: str
    onboarded_on: date
    data_window: tuple[date, date]


class CreditRead(ContractModel):
    transaction: RailCreditTransaction
    machine_label: PredictionLabel | None = None
    claim_label: PredictionLabel | None = None
    effective_label: PredictionLabel | None = None
    tier: EvidenceTier | None = None
    conflict: bool = False
    entry_refs: list[int] = Field(default_factory=list)


class CreditsResponse(ContractModel):
    items: list[CreditRead]
    next_cursor: str | None = None
    as_of: AwareDatetime


class CreditResponse(CreditRead):
    pass


class CreditByUtrResponse(CreditRead):
    pass


class PayerFact(ContractModel):
    key: str
    value: str
    entry_ref: int


class PayerHistoryResponse(ContractModel):
    merchant_id: MerchantId
    counterparty_id: CounterpartyId
    as_of: AwareDatetime
    strictly_prior_credit_count: Annotated[int, Field(ge=0)]
    channels: list[RailChannel]
    merchant_has_paid_them: bool
    twin_txn_ids: list[TransactionId]
    own_account_cue: bool
    surname_cue: bool
    payer_facts: list[PayerFact]


REQUEST_MODELS: tuple[type[ContractModel], ...] = ()
