"""General merchant, credit and payer-history read models."""

from __future__ import annotations

from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from ..common import (
    ContractModel,
    CounterpartyId,
    EvidenceTier,
    MerchantId,
    Money,
    PredictionLabel,
    TransactionId,
)
from .rails import RailChannel, RailTransaction


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
    transaction: RailTransaction
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

