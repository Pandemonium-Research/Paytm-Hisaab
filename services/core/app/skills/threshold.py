"""6.3: GST registration threshold verdict, crossing date, and forward projection."""

from __future__ import annotations

import math
from datetime import timedelta

from ..ledger.mutations import business_day
from ..ledger.projection import merchant
from ..schemas.api.skills import ThresholdRequest, ThresholdResponse
from .turnover_sales import (
    effective_as_of,
    first_crossing_day,
    load_billed_by_txn,
    load_credit_rows_between_business_days,
    load_period_credit_rows,
    ordered_period_contributions,
    sum_aggregate_in_rows,
    trailing_window_start,
)

THRESHOLD_GOODS_RUPEES = 4_000_000
THRESHOLD_SERVICES_RUPEES = 2_000_000


def _threshold_for_supply_kind(supply_kind: str) -> int:
    if supply_kind == "services":
        return THRESHOLD_SERVICES_RUPEES
    return THRESHOLD_GOODS_RUPEES


def _gst_is_unregistered(gst_status: str) -> bool:
    normalized = (gst_status or "").strip().casefold()
    return normalized in {"", "unregistered"}


def _format_rupees(amount: int) -> str:
    return f"₹{amount:,}"


def threshold(connection, body: ThresholdRequest) -> ThresholdResponse:
    merchant(connection, body.merchant_id)
    as_of = effective_as_of(connection, body.as_of)
    as_of_day = business_day(as_of)
    limit = _threshold_for_supply_kind(body.supply_kind)

    period_rows = load_period_credit_rows(
        connection, body.merchant_id, as_of, body.period_from, body.period_to,
    )
    billed_by_txn = load_billed_by_txn(connection, body.merchant_id, as_of)
    contributions = ordered_period_contributions(period_rows, billed_by_txn)
    crossed_on = first_crossing_day(
        contributions,
        limit,
        period_from=body.period_from,
        period_to=body.period_to,
    )

    projected_crossing_on = None
    trailing_60_day_run_rate = None
    warning_days = None

    should_project = (
        crossed_on is None
        and not body.exclusively_exempt
        and _gst_is_unregistered(body.gst_status)
        and body.aggregate_turnover <= limit
    )
    if should_project:
        window_start = trailing_window_start(as_of_day)
        trailing_rows = load_credit_rows_between_business_days(
            connection, body.merchant_id, as_of, window_start, as_of_day,
        )
        trailing_60_day_run_rate = sum_aggregate_in_rows(trailing_rows, billed_by_txn)
        daily_rate = trailing_60_day_run_rate / 60
        if daily_rate > 0:
            gap = limit - body.aggregate_turnover
            days_to_cross = math.ceil(gap / daily_rate)
            projected_crossing_on = as_of_day + timedelta(days=days_to_cross)
            warning_days = max(0, (projected_crossing_on - as_of_day).days)

    if body.exclusively_exempt:
        registration_required = False
        reason = (
            "The supplier deals exclusively in exempt supplies and need not register "
            "under CGST s.23, however high aggregate turnover goes."
        )
    elif not _gst_is_unregistered(body.gst_status):
        status = body.gst_status.strip()
        registration_required = False
        reason = (
            f"The merchant is already registered ({status}), so the registration threshold "
            "does not apply; a return-mismatch check is what matters instead."
        )
    else:
        registration_required = body.aggregate_turnover > limit
        if registration_required:
            reason = (
                f"Aggregate turnover {_format_rupees(body.aggregate_turnover)} is above the "
                f"{body.supply_kind} threshold of {_format_rupees(limit)}."
            )
        else:
            reason = (
                f"Aggregate turnover {_format_rupees(body.aggregate_turnover)} is at or below the "
                f"{body.supply_kind} threshold of {_format_rupees(limit)}."
            )

    return ThresholdResponse(
        threshold=limit,
        registration_required=registration_required,
        reason=reason,
        crossed_on=crossed_on,
        projected_crossing_on=projected_crossing_on,
        trailing_60_day_run_rate=trailing_60_day_run_rate,
        warning_days=warning_days,
    )
