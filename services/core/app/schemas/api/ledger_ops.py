"""Ledger mutation and trust-view contracts."""

from __future__ import annotations

from enum import Enum
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field, model_validator

from ..common import ContractModel, MerchantId, PredictionLabel, TransactionId
from ..ledger import (
    ClaimAnnotatedPayload,
    ClaimAnsweredPayload,
    LabelDisputedPayload,
    LabelProposedPayload,
    LedgerEntry,
    ProposalSource,
    QuestionAskedPayload,
)


AGENT_CONFIDENCE_CAP = 0.85


class LedgerProposalRequest(ContractModel):
    merchant_id: MerchantId
    txn_id: TransactionId
    proposal: LabelProposedPayload
    sim_at: AwareDatetime

    @model_validator(mode="after")
    def cap_agent_confidence(self) -> "LedgerProposalRequest":
        if (
            self.proposal.source is ProposalSource.AGENT
            and self.proposal.confidence > AGENT_CONFIDENCE_CAP
        ):
            raise ValueError(f"agent confidence must be at most {AGENT_CONFIDENCE_CAP}")
        return self


class LedgerProposalResponse(ContractModel):
    entry: LedgerEntry


class LedgerQuestionRequest(ContractModel):
    merchant_id: MerchantId
    txn_id: TransactionId
    question: QuestionAskedPayload
    sim_at: AwareDatetime


class LedgerQuestionResponse(ContractModel):
    entry: LedgerEntry


class ClaimAction(str, Enum):
    ANSWER = "answered"
    ANNOTATE = "annotated"
    DISPUTE = "disputed"


ClaimPayload = ClaimAnsweredPayload | ClaimAnnotatedPayload | LabelDisputedPayload


class LedgerClaimRequest(ContractModel):
    merchant_id: MerchantId
    txn_id: TransactionId
    action: ClaimAction
    claim: ClaimPayload
    sim_at: AwareDatetime

    @model_validator(mode="after")
    def action_matches_payload(self) -> "LedgerClaimRequest":
        expected = {
            ClaimAction.ANSWER: ClaimAnsweredPayload,
            ClaimAction.ANNOTATE: ClaimAnnotatedPayload,
            ClaimAction.DISPUTE: LabelDisputedPayload,
        }[self.action]
        if not isinstance(self.claim, expected):
            raise ValueError("claim payload does not match action")
        return self


class LedgerClaimResponse(ContractModel):
    entry: LedgerEntry
    payer_fact_updated: bool


class AnchorRead(ContractModel):
    anchor_id: str
    digest_sha256: str
    simulated: bool
    created_at: AwareDatetime
    ots_receipt: str | None = None
    git_commit_url: str | None = None


class LedgerVerifyResponse(ContractModel):
    merchant_id: MerchantId
    ok: bool
    broken_at: int | None = None
    first_disagreeing_anchor: AnchorRead | None = None


class LedgerEntriesResponse(ContractModel):
    entries: list[LedgerEntry]
    next_cursor: str | None = None


class AnchorsResponse(ContractModel):
    anchors: list[AnchorRead]


REQUEST_MODELS = (LedgerProposalRequest, LedgerQuestionRequest, LedgerClaimRequest)

