"""Administrative simulator and anchor-job contracts."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from ..common import ContractModel, MerchantId


class SimClockRequest(ContractModel):
    sim_at: AwareDatetime


class SimClockResponse(ContractModel):
    sim_at: AwareDatetime


class SimReplayRequest(ContractModel):
    split: str
    until: AwareDatetime


class SimReplayResponse(ContractModel):
    split: str
    sim_at: AwareDatetime
    transactions_replayed: Annotated[int, Field(ge=0)]
    events_replayed: Annotated[int, Field(ge=0)]


class SimResetRequest(ContractModel):
    split: str = "demo"


class SimResetResponse(ContractModel):
    split: str
    reset: bool
    sim_at: AwareDatetime


class SimTamperRequest(ContractModel):
    merchant_id: MerchantId
    chain_index: Annotated[int, Field(ge=0)]
    replacement_label: str


class SimTamperResponse(ContractModel):
    tampered: bool
    merchant_id: MerchantId
    chain_index: int


class RunAnchorRequest(ContractModel):
    sim_at: AwareDatetime
    simulated: bool


class RunAnchorResponse(ContractModel):
    anchor_id: str
    digest_sha256: str
    simulated: bool


REQUEST_MODELS = (
    SimClockRequest,
    SimReplayRequest,
    SimResetRequest,
    SimTamperRequest,
    RunAnchorRequest,
)

