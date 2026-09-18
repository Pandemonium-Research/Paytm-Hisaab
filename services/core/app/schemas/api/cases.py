"""Case, evidence-pack, approval and outbox contracts."""

from __future__ import annotations

from typing import Literal

from pydantic import AwareDatetime

from ..common import CaseId, ContractModel, MerchantId, PackId
from ..ledger import LedgerEntry


class CreateCaseRequest(ContractModel):
    merchant_id: MerchantId
    case_type: Literal["freeze", "notice"]
    trigger_ref: str
    sim_at: AwareDatetime


class CreateCaseResponse(ContractModel):
    case_id: CaseId
    status: Literal["open"] = "open"
    ledger_entry: LedgerEntry


class BuildPackRequest(ContractModel):
    merchant_id: MerchantId
    case_id: CaseId
    pack_type: Literal["freeze", "notice"]
    sim_at: AwareDatetime


class BuildPackResponse(ContractModel):
    pack_id: PackId
    case_id: CaseId
    json_path: str
    pdf_path: str
    pdf_sha256: str
    ledger_entry: LedgerEntry


class ApprovePackRequest(ContractModel):
    officer_ref: str
    note: str | None = None
    sim_at: AwareDatetime


class ApprovePackResponse(ContractModel):
    pack_id: PackId
    status: Literal["approved"] = "approved"
    workflow_resumed: bool
    ledger_entry: LedgerEntry


class RejectPackRequest(ContractModel):
    officer_ref: str
    reason: str
    sim_at: AwareDatetime


class RejectPackResponse(ContractModel):
    pack_id: PackId
    status: Literal["rejected"] = "rejected"
    workflow_resumed: bool
    ledger_entry: LedgerEntry


class SendPackRequest(ContractModel):
    destination: str
    sim_at: AwareDatetime


class SendPackResponse(ContractModel):
    pack_id: PackId
    sent: bool
    delivery_ref: str
    simulated: Literal[True] = True
    ledger_entry: LedgerEntry


REQUEST_MODELS = (
    CreateCaseRequest,
    BuildPackRequest,
    ApprovePackRequest,
    RejectPackRequest,
    SendPackRequest,
)

