"""6.5: decide whether a freeze case needs a specialist instead of routine approval.

Thresholds are imported from ``schemas.api.skills`` (TODO 1.3 / plan §22); they are provisional
and not settled law until verified.
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import text

from ..schemas.api.skills import (
    ESCALATION_REPEAT_FREEZE_DAYS,
    ESCALATION_SMALL_SUM_LIMIT_RUPEES,
    ESCALATION_WEAK_SHARE,
    ESCALATION_WEAK_TIERS,
    EscalationCheckRequest,
    EscalationCheckResponse,
)
from ..schemas.common import PredictionLabel

_ORDINARY_SALE_LABELS = frozenset(
    {PredictionLabel.TAXABLE_SUPPLY, PredictionLabel.EXEMPT_SUPPLY},
)


def _format_rupees(amount: int) -> str:
    return f"₹{amount:,}"


def _weak_tier_reason() -> str:
    return (
        "The disputed credit is not backed by a bill or a rule; it rests on a merchant answer "
        "or evidence recorded after the freeze notice."
    )


def escalation_check(connection, body: EscalationCheckRequest) -> EscalationCheckResponse:
    case = connection.execute(
        text("SELECT case_id FROM ops.cases WHERE case_id = :case"),
        {"case": body.case_id},
    ).mappings().one_or_none()
    if case is None:
        raise HTTPException(404, f"No case {body.case_id} was found.")

    reasons: list[str] = []

    if body.disputed_amount > ESCALATION_SMALL_SUM_LIMIT_RUPEES:
        reasons.append(
            f"The disputed amount of {_format_rupees(body.disputed_amount)} is above the "
            f"{_format_rupees(ESCALATION_SMALL_SUM_LIMIT_RUPEES)} small-sum limit."
        )

    if body.disputed_tier in ESCALATION_WEAK_TIERS:
        reasons.append(_weak_tier_reason())

    if body.effective_label not in _ORDINARY_SALE_LABELS:
        reasons.append(
            f"The effective label is {body.effective_label.value}, not an ordinary taxable or "
            "exempt supply."
        )

    if body.claim_conflicts_with_bill:
        reasons.append("The merchant's claim conflicts with the bill on record.")

    if body.merchant_disputed_label:
        reasons.append("The merchant has disputed the proposed label.")

    if body.tier_3_4_share > ESCALATION_WEAK_SHARE:
        pct = int(ESCALATION_WEAK_SHARE * 100)
        reasons.append(
            f"The share of period turnover supported only by weak evidence (tiers 3 and 4) "
            f"is above {pct}%."
        )

    if (
        body.prior_freeze_days_ago is not None
        and body.prior_freeze_days_ago <= ESCALATION_REPEAT_FREEZE_DAYS
    ):
        reasons.append(
            f"A prior freeze on this merchant was within the last "
            f"{ESCALATION_REPEAT_FREEZE_DAYS} days."
        )

    return EscalationCheckResponse(escalate=bool(reasons), reasons=reasons)
