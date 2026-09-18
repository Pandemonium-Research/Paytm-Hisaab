"""Public endpoint contracts, grouped by API area in the implementation modules."""

from __future__ import annotations

from . import (
    app_screens,
    assistant,
    cases,
    guards,
    ledger_ops,
    ops,
    prompts,
    rails,
    reads,
    sim,
    skills,
)

_MODULES = (
    rails,
    reads,
    skills,
    ledger_ops,
    cases,
    guards,
    ops,
    app_screens,
    assistant,
    sim,
    prompts,
)

# Re-export only types defined by these modules, not their imported helpers.
for _module in _MODULES:
    for _name, _value in vars(_module).items():
        if isinstance(_value, type) and _value.__module__ == _module.__name__:
            globals()[_name] = _value

REQUEST_MODELS = tuple(
    model for module in _MODULES for model in getattr(module, "REQUEST_MODELS", ())
)

# Route -> (body model, response model). ``None`` means the route has no JSON body.
ENDPOINT_MODELS = {
    "POST /rails/credits": (rails.RailsCreditsRequest, rails.RailsCreditsResponse),
    "POST /rails/bills": (rails.RailsBillsRequest, rails.RailsBillsResponse),
    "POST /rails/events": (rails.RailsEventsRequest, rails.RailsEventsResponse),
    "GET /merchants/{id}": (None, reads.MerchantResponse),
    "GET /credits": (None, reads.CreditsResponse),
    "GET /credits/{txn}": (None, reads.CreditResponse),
    "GET /credits/by-utr/{utr}": (None, reads.CreditByUtrResponse),
    "GET /payers/{cp}/history": (None, reads.PayerHistoryResponse),
    "POST /skills/classify-rules": (skills.ClassifyRulesRequest, skills.ClassifyRulesResponse),
    "POST /ledger/proposals": (ledger_ops.LedgerProposalRequest, ledger_ops.LedgerProposalResponse),
    "POST /skills/select-questions": (
        skills.SelectQuestionsRequest,
        skills.SelectQuestionsResponse,
    ),
    "POST /ledger/questions": (ledger_ops.LedgerQuestionRequest, ledger_ops.LedgerQuestionResponse),
    "POST /ledger/claims": (ledger_ops.LedgerClaimRequest, ledger_ops.LedgerClaimResponse),
    "POST /skills/turnover": (skills.TurnoverRequest, skills.TurnoverResponse),
    "POST /skills/threshold": (skills.ThresholdRequest, skills.ThresholdResponse),
    "POST /skills/isolate": (skills.IsolateRequest, skills.IsolateResponse),
    "POST /skills/tiers": (skills.TiersRequest, skills.TiersResponse),
    "POST /skills/escalation-check": (
        skills.EscalationCheckRequest,
        skills.EscalationCheckResponse,
    ),
    "POST /cases": (cases.CreateCaseRequest, cases.CreateCaseResponse),
    "POST /packs": (cases.BuildPackRequest, cases.BuildPackResponse),
    "POST /guards/numbers": (guards.GuardRequest, guards.GuardResponse),
    "POST /guards/citations": (guards.GuardRequest, guards.GuardResponse),
    "POST /guards/no-innocence": (guards.GuardRequest, guards.GuardResponse),
    "POST /guards/extraction": (guards.GuardRequest, guards.GuardResponse),
    "POST /guards/language": (guards.GuardRequest, guards.GuardResponse),
    "POST /packs/{id}/approve": (cases.ApprovePackRequest, cases.ApprovePackResponse),
    "POST /packs/{id}/reject": (cases.RejectPackRequest, cases.RejectPackResponse),
    "POST /outbox/{pack}/send": (cases.SendPackRequest, cases.SendPackResponse),
    "GET /ledger/verify": (None, ledger_ops.LedgerVerifyResponse),
    "GET /ledger/{m}/entries": (None, ledger_ops.LedgerEntriesResponse),
    "GET /anchors": (None, ledger_ops.AnchorsResponse),
    "POST /sim/clock": (sim.SimClockRequest, sim.SimClockResponse),
    "POST /sim/replay": (sim.SimReplayRequest, sim.SimReplayResponse),
    "POST /sim/reset": (sim.SimResetRequest, sim.SimResetResponse),
    "POST /sim/tamper": (sim.SimTamperRequest, sim.SimTamperResponse),
    "POST /anchors/run": (sim.RunAnchorRequest, sim.RunAnchorResponse),
    "POST /assistant/inbound": (
        assistant.AssistantInboundRequest,
        assistant.AssistantInboundResponse,
    ),
    "GET /assistant/stream": (None, assistant.AssistantStreamResponse),
    "POST /assistant/outbound": (
        assistant.AssistantOutboundRequest,
        assistant.AssistantOutboundResponse,
    ),
    "GET /app/home": (None, app_screens.AppHomeResponse),
    "GET /app/payments": (None, app_screens.AppPaymentsResponse),
    "GET /app/payments/{txn}": (None, app_screens.AppPaymentDetailResponse),
    "GET /app/cases": (None, app_screens.AppCasesResponse),
    "GET /app/turnover": (None, app_screens.AppTurnoverResponse),
    "GET /app/officer/queue": (None, app_screens.OfficerQueueResponse),
    "GET /app/officer/cases/{id}": (None, app_screens.OfficerCaseResponse),
    "POST /app/push/subscribe": (ops.PushSubscribeRequest, ops.PushSubscribeResponse),
    "GET /prompts/{name}": (None, prompts.PromptResponse),
    "GET /config": (None, ops.ConfigResponse),
}

AGENT_CONFIDENCE_CAP = ledger_ops.AGENT_CONFIDENCE_CAP
QUESTION_LOW_CONFIDENCE = skills.QUESTION_LOW_CONFIDENCE
QUESTION_NON_SALE_MIN_RUPEES = skills.QUESTION_NON_SALE_MIN_RUPEES
QUESTION_NEW_PAYER_SALE_MIN_RUPEES = skills.QUESTION_NEW_PAYER_SALE_MIN_RUPEES
QUESTION_NEW_PAYER_MAX_PRIOR_CREDITS = skills.QUESTION_NEW_PAYER_MAX_PRIOR_CREDITS
QUESTION_ABSOLUTE_MIN_RUPEES = skills.QUESTION_ABSOLUTE_MIN_RUPEES
QUESTION_THRESHOLD_PROXIMITY_FRACTION = skills.QUESTION_THRESHOLD_PROXIMITY_FRACTION
QUESTION_THRESHOLD_PROXIMITY_MULTIPLIER = skills.QUESTION_THRESHOLD_PROXIMITY_MULTIPLIER
QUESTION_DAILY_LIMIT = skills.QUESTION_DAILY_LIMIT
QUESTION_EXPIRY_DAYS = skills.QUESTION_EXPIRY_DAYS
ESCALATION_SMALL_SUM_LIMIT_RUPEES = skills.ESCALATION_SMALL_SUM_LIMIT_RUPEES
ESCALATION_WEAK_TIERS = skills.ESCALATION_WEAK_TIERS
ESCALATION_WEAK_SHARE = skills.ESCALATION_WEAK_SHARE
ESCALATION_REPEAT_FREEZE_DAYS = skills.ESCALATION_REPEAT_FREEZE_DAYS

__all__ = sorted(
    {
        "REQUEST_MODELS",
        "ENDPOINT_MODELS",
        "AGENT_CONFIDENCE_CAP",
        "QUESTION_LOW_CONFIDENCE",
        "QUESTION_NON_SALE_MIN_RUPEES",
        "QUESTION_NEW_PAYER_SALE_MIN_RUPEES",
        "QUESTION_NEW_PAYER_MAX_PRIOR_CREDITS",
        "QUESTION_ABSOLUTE_MIN_RUPEES",
        "QUESTION_THRESHOLD_PROXIMITY_FRACTION",
        "QUESTION_THRESHOLD_PROXIMITY_MULTIPLIER",
        "QUESTION_DAILY_LIMIT",
        "QUESTION_EXPIRY_DAYS",
        "ESCALATION_SMALL_SUM_LIMIT_RUPEES",
        "ESCALATION_WEAK_TIERS",
        "ESCALATION_WEAK_SHARE",
        "ESCALATION_REPEAT_FREEZE_DAYS",
        *(
            name
            for module in _MODULES
            for name, value in vars(module).items()
            if isinstance(value, type) and value.__module__ == module.__name__
        ),
    }
)
