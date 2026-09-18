"""Configuration and cross-app operational contracts."""

from __future__ import annotations

from typing import Literal

from ..common import ContractModel, MerchantId


class PushSubscriptionKeys(ContractModel):
    p256dh: str
    auth: str


class PushSubscribeRequest(ContractModel):
    app: Literal["merchant", "officer"]
    merchant_id: MerchantId | None = None
    endpoint: str
    expiration_time: int | None = None
    keys: PushSubscriptionKeys


class PushSubscribeResponse(ContractModel):
    subscription_id: str
    subscribed: bool


class ConfigResponse(ContractModel):
    # TODO(1.3): Section 7 does not specify /config fields; these are the PWA boot minimum.
    environment: str
    live: bool
    default_locale: str
    supported_locales: list[str]
    vapid_public_key: str | None = None


REQUEST_MODELS = (PushSubscribeRequest,)
