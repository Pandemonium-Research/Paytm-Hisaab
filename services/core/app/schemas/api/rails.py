"""Rails ingest contracts matching the synthetic visible files."""

from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from ..common import ContractModel, MerchantId, Money, TransactionId


class TransactionDirection(str, Enum):
    CREDIT = "CR"
    DEBIT = "DR"


class RailChannel(str, Enum):
    UPI_QR = "UPI_QR"
    UPI_POS = "UPI_POS"
    CARD_POS = "CARD_POS"
    UPI_INTENT = "UPI_INTENT"
    IMPS = "IMPS"
    BANK_TRANSFER = "BANK_TRANSFER"
    UPI_REVERSAL = "UPI_REVERSAL"
    UPI_OUT = "UPI_OUT"
    REFUND = "REFUND"


class RailTransaction(ContractModel):
    txn_id: TransactionId
    merchant_id: MerchantId
    ts: AwareDatetime
    direction: TransactionDirection
    amount: Money
    channel: RailChannel
    counterparty_id: str
    counterparty_handle: str
    counterparty_name: str
    terminal_id: str | None = None
    pos_bill_id: str | None = None
    utr: Annotated[str, Field(pattern=r"^\d{12}$")]
    orig_txn_id: TransactionId | None = None
    note: str = ""


CreditRailChannel = Literal[
    RailChannel.UPI_QR,
    RailChannel.UPI_POS,
    RailChannel.CARD_POS,
    RailChannel.UPI_INTENT,
    RailChannel.IMPS,
    RailChannel.BANK_TRANSFER,
    RailChannel.UPI_REVERSAL,
]
DebitRailChannel = Literal[RailChannel.UPI_OUT, RailChannel.REFUND]


class RailCreditTransaction(RailTransaction):
    direction: Literal[TransactionDirection.CREDIT]
    channel: CreditRailChannel


class RailDebitTransaction(RailTransaction):
    direction: Literal[TransactionDirection.DEBIT]
    channel: DebitRailChannel
    # The simulator writes an empty CSV cell; JSON replayers may normalise that to null.
    pos_bill_id: Literal[""] | None = None


class RailsCreditsRequest(ContractModel):
    transactions: list[RailCreditTransaction]
    sim_at: AwareDatetime | None = None


class RailsCreditsResponse(ContractModel):
    accepted: int
    duplicate_txn_ids: list[TransactionId] = Field(default_factory=list)


class RailsDebitsRequest(ContractModel):
    transactions: list[RailDebitTransaction]
    sim_at: AwareDatetime | None = None


class RailsDebitsResponse(ContractModel):
    accepted: int
    duplicate_txn_ids: list[TransactionId] = Field(default_factory=list)


class PosBillLine(ContractModel):
    pos_bill_id: str
    txn_id: TransactionId
    merchant_id: MerchantId
    line_no: Annotated[int, Field(ge=1)]
    item: str
    hsn: str
    qty: str
    unit: str
    rate: str
    line_amount: Money


class RailsBillsRequest(ContractModel):
    lines: list[PosBillLine]
    sim_at: AwareDatetime | None = None


class RailsBillsResponse(ContractModel):
    accepted_lines: int
    linked_bill_ids: list[str]


class Authority(ContractModel):
    unit: str
    state: str
    city: str


class _RailEventBase(ContractModel):
    event_id: str
    merchant_id: MerchantId
    ts: AwareDatetime


class LienMarkedEvent(_RailEventBase):
    type: Literal["lien_marked"]
    freeze_type: str
    scope: str
    authority: Authority
    ncrp_ack: str
    case_ref: str
    disputed_amount: Money
    disputed_date: date
    disputed_utr: str
    intimation: str


class PaymentDeclinedEvent(_RailEventBase):
    type: Literal["payment_declined"]
    direction: Literal[TransactionDirection.DEBIT]
    amount: Money
    channel: DebitRailChannel
    counterparty_id: str
    counterparty_name: str
    counterparty_handle: str
    reason_code: str
    reason: str
    purpose: str


class LeaInquiryEvent(_RailEventBase):
    type: Literal["lea_inquiry"]
    authority: Authority
    ncrp_ack: str
    case_ref: str
    amount: Money
    date: date
    utr: str
    request: str
    confidentiality: str


class NoticeServedEvent(_RailEventBase):
    type: Literal["notice_served"]
    document: str
    photo: str | None
    note: str


class ReturnFiledEvent(_RailEventBase):
    type: Literal["return_filed"]
    form: Literal["CMP-08"]
    period: str
    declared_turnover: Money


RailEvent = Annotated[
    LienMarkedEvent
    | PaymentDeclinedEvent
    | LeaInquiryEvent
    | NoticeServedEvent
    | ReturnFiledEvent,
    Field(discriminator="type"),
]


class RailsEventsRequest(ContractModel):
    events: list[RailEvent]
    sim_at: AwareDatetime | None = None


class RailsEventsResponse(ContractModel):
    accepted: int
    opened_case_ids: list[str] = Field(default_factory=list)


REQUEST_MODELS = (
    RailsCreditsRequest,
    RailsDebitsRequest,
    RailsBillsRequest,
    RailsEventsRequest,
)
