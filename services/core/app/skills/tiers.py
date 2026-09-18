"""6.1: aggregate evidence tiers at a case-relative business-time cutoff."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import text

from ..clock import sim_now
from ..schemas.api.skills import TierAggregate, TiersRequest, TiersResponse
from ..schemas.common import EvidenceTier


def _effective_as_of(connection, as_of: datetime) -> datetime:
    now = sim_now(connection)
    return min(as_of, now)


def tiers(connection, body: TiersRequest) -> TiersResponse:
    as_of = _effective_as_of(connection, body.as_of)
    case = connection.execute(
        text("""SELECT * FROM ops.cases WHERE case_id = :case AND merchant_id = :merchant
                AND opened_at <= :as_of"""),
        {"case": body.case_id, "merchant": body.merchant_id, "as_of": as_of},
    ).mappings().one_or_none()
    if case is None:
        raise HTTPException(404, f"No case {body.case_id} for this merchant at that time.")

    rows = connection.execute(
        text("""SELECT v.tier, sum(c.amount) AS amount, count(*) AS count
                FROM rails.credits c
                JOIN ledger.current_view(:merchant, :as_of, :opened_at) v USING (txn_id)
                WHERE c.merchant_id = :merchant AND c.ts <= :as_of
                  AND (c.ts AT TIME ZONE 'Asia/Kolkata')::date
                      BETWEEN :period_from AND :period_to
                  AND v.tier IS NOT NULL
                GROUP BY v.tier"""),
        {
            "merchant": body.merchant_id,
            "as_of": as_of,
            "opened_at": body.opened_at,
            "period_from": body.period_from,
            "period_to": body.period_to,
        },
    ).mappings().all()
    found = {EvidenceTier(row["tier"]): (int(row["amount"]), int(row["count"])) for row in rows}
    totals = [
        TierAggregate(tier=tier, amount=found.get(tier, (0, 0))[0], count=found.get(tier, (0, 0))[1])
        for tier in EvidenceTier
    ]
    total_amount = sum(item.amount for item in totals)
    strong_amount = totals[0].amount + totals[1].amount
    return TiersResponse(
        totals=totals,
        strong_shape_fraction=strong_amount / total_amount if total_amount else 0.0,
    )
