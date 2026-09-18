"""6.2: aggregate turnover for a period with billed splits and unbilled apportionment."""

from __future__ import annotations

from ..ledger.projection import merchant
from ..schemas.api.skills import (
    ExcludedTransaction,
    TurnoverRequest,
    TurnoverResponse,
    TurnoverWorking,
)
from ..schemas.common import PredictionLabel
from .turnover_sales import (
    SALE_LABELS,
    effective_as_of,
    load_billed_by_txn,
    load_period_credit_rows,
)

EXCLUSION_REASONS = {
    PredictionLabel.INTER_ACCOUNT.value: "Transfer from a linked own account.",
    PredictionLabel.DUPLICATE.value: "A duplicate of another payment.",
    PredictionLabel.REFUND_REVERSAL.value: "A refund or reversal, not a supply.",
    PredictionLabel.PERSONAL_TRANSFER.value: "Family or personal money, not a supply.",
    PredictionLabel.NON_BUSINESS.value: "Non-business money, such as a loan or a gift.",
    PredictionLabel.UNCLASSIFIED.value: "Not yet classified.",
}


def _usable_label(label: str | None) -> bool:
    return label is not None and label != PredictionLabel.UNCLASSIFIED.value


def turnover(connection, body: TurnoverRequest) -> TurnoverResponse:
    merchant(connection, body.merchant_id)
    as_of = effective_as_of(connection, body.as_of)
    rows = load_period_credit_rows(
        connection, body.merchant_id, as_of, body.period_from, body.period_to,
    )
    billed_by_txn = load_billed_by_txn(connection, body.merchant_id, as_of)

    billed_exempt = 0
    billed_taxable = 0
    unbilled_total = 0
    bill_only_turnover = 0
    excluded: list[ExcludedTransaction] = []
    classified_amount = 0
    period_total = 0

    for row in rows:
        amount = int(row["amount"])
        period_total += amount
        label = row["effective_label"]
        if label == PredictionLabel.UNCLASSIFIED.value:
            label = None

        if label in SALE_LABELS:
            classified_amount += amount
            bill = billed_by_txn.get(row["txn_id"])
            if bill is not None:
                billed_exempt += bill[0]
                billed_taxable += bill[1]
            else:
                unbilled_total += amount
        elif _usable_label(label):
            excluded.append(
                ExcludedTransaction(
                    txn_id=row["txn_id"],
                    amount=amount,
                    label=label,
                    reason=EXCLUSION_REASONS.get(label, "Excluded from turnover."),
                )
            )
        elif label is None:
            bill = billed_by_txn.get(row["txn_id"])
            if bill is not None:
                classified_amount += amount
                billed_exempt += bill[0]
                billed_taxable += bill[1]
                bill_only_turnover += bill[0] + bill[1]
            else:
                excluded.append(
                    ExcludedTransaction(
                        txn_id=row["txn_id"],
                        amount=amount,
                        label=PredictionLabel.UNCLASSIFIED,
                        reason=EXCLUSION_REASONS[PredictionLabel.UNCLASSIFIED.value],
                    )
                )
        else:
            excluded.append(
                ExcludedTransaction(
                    txn_id=row["txn_id"],
                    amount=amount,
                    label=label,
                    reason=EXCLUSION_REASONS.get(label, "Excluded from turnover."),
                )
            )

    excluded.sort(key=lambda item: item.txn_id)

    billed_sales_total = billed_exempt + billed_taxable
    exempt_share = billed_exempt / billed_sales_total if billed_sales_total > 0 else 0.0
    estimated_unbilled_exempt = round(unbilled_total * exempt_share)
    estimated_unbilled_taxable = unbilled_total - estimated_unbilled_exempt

    taxable = billed_taxable + estimated_unbilled_taxable
    exempt = billed_exempt + estimated_unbilled_exempt
    aggregate = taxable + exempt

    coverage_fraction = classified_amount / period_total if period_total else 1.0

    share_pct = exempt_share * 100
    workings: list[TurnoverWorking] = [
        TurnoverWorking(description="Billed taxable supplies.", amount=billed_taxable, estimated=False),
        TurnoverWorking(description="Billed exempt supplies.", amount=billed_exempt, estimated=False),
        TurnoverWorking(
            description=f"Unbilled sales apportioned at {share_pct:.1f}% exempt share.",
            amount=unbilled_total,
            estimated=True,
        ),
        TurnoverWorking(
            description="Aggregate turnover.",
            amount=aggregate,
            estimated=unbilled_total > 0,
        ),
    ]
    if aggregate:
        billed_share = billed_sales_total / aggregate
        workings.append(
            TurnoverWorking(
                description=f"Billed share of turnover: {billed_share * 100:.1f}% of aggregate rests on itemised bills.",
                amount=billed_sales_total,
                estimated=False,
            )
        )
    if billed_sales_total == 0 and unbilled_total > 0:
        workings.append(
            TurnoverWorking(
                description="No billed sales in the period; unbilled sales were treated as taxable.",
                amount=unbilled_total,
                estimated=True,
            )
        )
    if bill_only_turnover > 0:
        workings.append(
            TurnoverWorking(
                description=(
                    "Turnover from itemised bills with no recorded supply label "
                    "(bill classification only)."
                ),
                amount=bill_only_turnover,
                estimated=False,
            )
        )

    return TurnoverResponse(
        merchant_id=body.merchant_id,
        taxable=taxable,
        exempt=exempt,
        aggregate=aggregate,
        estimated_unbilled_taxable=estimated_unbilled_taxable,
        estimated_unbilled_exempt=estimated_unbilled_exempt,
        excluded=excluded,
        coverage_fraction=coverage_fraction,
        workings=workings,
    )
