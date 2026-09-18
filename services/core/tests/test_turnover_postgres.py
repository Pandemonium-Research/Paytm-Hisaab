"""Turnover aggregates sales, apportions unbilled QR credits, and lists exclusions."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from test_payments_postgres import api, payment, propose, request  # noqa: F401
from test_stubs import NOW


pytestmark = pytest.mark.postgres

PERIOD_FROM = "2026-03-21"
PERIOD_TO = "2026-03-21"
DAY_TS = "2026-03-21T10:00:00+05:30"


def turnover_body(profile, **extra):
    return {
        "merchant_id": profile["merchant_id"],
        "period_from": PERIOD_FROM,
        "period_to": PERIOD_TO,
        "as_of": NOW,
        **extra,
    }


def turnover(client, profile, **extra):
    response = request(client, "/skills/turnover", turnover_body(profile, **extra), "evidence")
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["aggregate"] == data["taxable"] + data["exempt"]
    return data


def catalog_item(connection, *, exempt: bool):
    item = f"Item-{uuid4().hex}"
    connection.execute(
        text("INSERT INTO rails.hsn_catalog (item, hsn, exempt) VALUES (:item, '9999', :exempt)"),
        {"item": item, "exempt": exempt},
    )
    return item


def post_bill(client, profile, value, lines, sim_at=NOW):
    response = request(
        client,
        "/rails/bills",
        {"sim_at": sim_at, "lines": lines},
        "rails",
    )
    assert response.status_code == 200, response.text


def billed_sale(client, connection, profile, amount, *, exempt_line: bool, label="taxable_supply"):
    bill_id = f"B-{uuid4().hex}"
    item = catalog_item(connection, exempt=exempt_line)
    value = payment(
        client,
        profile,
        amount=amount,
        bill=bill_id,
        channel="UPI_POS",
        ts=DAY_TS,
    )
    post_bill(
        client,
        profile,
        value,
        [{
            "pos_bill_id": bill_id,
            "txn_id": value["txn_id"],
            "merchant_id": profile["merchant_id"],
            "line_no": 1,
            "item": item,
            "hsn": "9999",
            "qty": "1",
            "unit": "item",
            "rate": str(amount),
            "line_amount": amount,
        }],
    )
    propose(client, value, label)
    return value


def mixed_bill_sale(client, connection, profile, exempt_amount, taxable_amount, label="exempt_supply"):
    bill_id = f"B-{uuid4().hex}"
    exempt_item = catalog_item(connection, exempt=True)
    taxable_item = catalog_item(connection, exempt=False)
    total = exempt_amount + taxable_amount
    value = payment(
        client,
        profile,
        amount=total,
        bill=bill_id,
        channel="UPI_POS",
        ts=DAY_TS,
    )
    post_bill(
        client,
        profile,
        value,
        [
            {
                "pos_bill_id": bill_id,
                "txn_id": value["txn_id"],
                "merchant_id": profile["merchant_id"],
                "line_no": 1,
                "item": exempt_item,
                "hsn": "9999",
                "qty": "1",
                "unit": "item",
                "rate": str(exempt_amount),
                "line_amount": exempt_amount,
            },
            {
                "pos_bill_id": bill_id,
                "txn_id": value["txn_id"],
                "merchant_id": profile["merchant_id"],
                "line_no": 2,
                "item": taxable_item,
                "hsn": "9999",
                "qty": "1",
                "unit": "item",
                "rate": str(taxable_amount),
                "line_amount": taxable_amount,
            },
        ],
    )
    propose(client, value, label)
    return value


def billed_sale_without_label(client, connection, profile, amount, *, exempt_line: bool):
    bill_id = f"B-{uuid4().hex}"
    item = catalog_item(connection, exempt=exempt_line)
    value = payment(
        client,
        profile,
        amount=amount,
        bill=bill_id,
        channel="UPI_POS",
        ts=DAY_TS,
    )
    post_bill(
        client,
        profile,
        value,
        [{
            "pos_bill_id": bill_id,
            "txn_id": value["txn_id"],
            "merchant_id": profile["merchant_id"],
            "line_no": 1,
            "item": item,
            "hsn": "9999",
            "qty": "1",
            "unit": "item",
            "rate": str(amount),
            "line_amount": amount,
        }],
    )
    return value


def test_fully_billed_period_matches_line_split(api):
    client, connection, profile = api
    billed_sale(client, connection, profile, 2000, exempt_line=False)
    billed_sale(client, connection, profile, 1500, exempt_line=True, label="exempt_supply")

    data = turnover(client, profile)
    assert data["taxable"] == 2000
    assert data["exempt"] == 1500
    assert data["aggregate"] == 3500
    assert data["estimated_unbilled_taxable"] == 0
    assert data["estimated_unbilled_exempt"] == 0
    assert data["coverage_fraction"] == 1.0
    assert data["excluded"] == []


def test_mixed_bill_splits_by_line_not_credit_label(api):
    client, connection, profile = api
    mixed_bill_sale(client, connection, profile, 1000, 2000, label="exempt_supply")

    data = turnover(client, profile)
    assert data["taxable"] == 2000
    assert data["exempt"] == 1000
    assert data["aggregate"] == 3000
    assert data["estimated_unbilled_taxable"] == 0
    assert data["estimated_unbilled_exempt"] == 0


def test_unbilled_sales_apportioned_with_exact_rounding(api):
    client, connection, profile = api
    billed_sale(client, connection, profile, 200, exempt_line=False)
    billed_sale(client, connection, profile, 100, exempt_line=True, label="exempt_supply")
    unbilled = payment(client, profile, amount=100, ts=DAY_TS)
    propose(client, unbilled, "taxable_supply")

    data = turnover(client, profile)
    assert data["estimated_unbilled_exempt"] == 33
    assert data["estimated_unbilled_taxable"] == 67
    assert data["estimated_unbilled_exempt"] + data["estimated_unbilled_taxable"] == 100
    assert data["taxable"] == 200 + 67
    assert data["exempt"] == 100 + 33


def test_no_billed_sales_treats_unbilled_as_taxable(api):
    client, connection, profile = api
    unbilled = payment(client, profile, amount=500, ts=DAY_TS)
    propose(client, unbilled, "taxable_supply")

    data = turnover(client, profile)
    assert data["taxable"] == 500
    assert data["exempt"] == 0
    assert data["estimated_unbilled_taxable"] == 500
    assert data["estimated_unbilled_exempt"] == 0
    assert any(
        "No billed sales" in line["description"] and line["estimated"]
        for line in data["workings"]
    )


def test_non_sale_labels_land_in_excluded(api):
    client, connection, profile = api
    own = payment(
        client,
        profile,
        amount=9000,
        channel="IMPS",
        handle=profile["linked_own_accounts"][0],
        ts=DAY_TS,
    )
    propose(client, own, "inter_account")
    duplicate = payment(client, profile, amount=1100, ts=DAY_TS)
    propose(client, duplicate, "duplicate")

    data = turnover(client, profile)
    assert data["aggregate"] == 0
    assert data["taxable"] == 0
    assert data["exempt"] == 0
    by_id = {row["txn_id"]: row for row in data["excluded"]}
    assert by_id[own["txn_id"]]["label"] == "inter_account"
    assert by_id[own["txn_id"]]["reason"] == "Transfer from a linked own account."
    assert by_id[duplicate["txn_id"]]["label"] == "duplicate"
    assert by_id[duplicate["txn_id"]]["reason"] == "A duplicate of another payment."


def test_unclassified_credit_reduces_coverage(api):
    client, connection, profile = api
    labelled = payment(client, profile, amount=1000, ts=DAY_TS)
    propose(client, labelled, "taxable_supply")
    silent = payment(client, profile, amount=1000, ts=DAY_TS)

    data = turnover(client, profile)
    assert data["coverage_fraction"] == 0.5
    assert len(data["excluded"]) == 1
    assert data["excluded"][0]["txn_id"] == silent["txn_id"]
    assert data["excluded"][0]["label"] == "unclassified"
    assert data["excluded"][0]["reason"] == "Not yet classified."


def test_period_filter_excludes_outside_business_days(api):
    client, connection, profile = api
    inside = payment(client, profile, amount=1000, ts=DAY_TS)
    propose(client, inside, "taxable_supply")
    outside = payment(client, profile, amount=5000, ts="2026-03-20T10:00:00+05:30")
    propose(client, outside, "taxable_supply")

    data = turnover(client, profile)
    assert data["aggregate"] == 1000
    assert data["taxable"] == 1000


def test_as_of_hides_future_credits_even_inside_period(api):
    client, connection, profile = api
    late = payment(client, profile, amount=8000, ts="2026-03-21T18:00:00+05:30")
    propose(client, late, "taxable_supply")

    data = turnover(client, profile, as_of="2026-03-21T12:00:00+05:30")
    assert data["aggregate"] == 0
    assert data["excluded"] == []


def test_billed_credit_without_label_counts_by_line_split(api):
    client, connection, profile = api
    value = billed_sale_without_label(client, connection, profile, 2500, exempt_line=False)

    data = turnover(client, profile)
    assert data["taxable"] == 2500
    assert data["exempt"] == 0
    assert data["aggregate"] == 2500
    assert data["excluded"] == []
    assert any(
        "no recorded supply label" in line["description"].lower()
        for line in data["workings"]
    )


def test_billed_credit_without_label_counts_as_classified_for_coverage(api):
    client, connection, profile = api
    billed_sale_without_label(client, connection, profile, 3000, exempt_line=True)

    data = turnover(client, profile)
    assert data["coverage_fraction"] == 1.0
    assert data["excluded"] == []


def test_explicit_non_sale_label_beats_linked_bill(api):
    client, connection, profile = api
    value = billed_sale_without_label(client, connection, profile, 1200, exempt_line=False)
    propose(client, value, "duplicate")

    data = turnover(client, profile)
    assert data["aggregate"] == 0
    assert len(data["excluded"]) == 1
    assert data["excluded"][0]["txn_id"] == value["txn_id"]
    assert data["excluded"][0]["label"] == "duplicate"


def test_credit_without_label_or_bill_stays_unclassified(api):
    client, connection, profile = api
    silent = payment(client, profile, amount=750, ts=DAY_TS)

    data = turnover(client, profile)
    assert data["aggregate"] == 0
    assert len(data["excluded"]) == 1
    assert data["excluded"][0]["txn_id"] == silent["txn_id"]
    assert data["excluded"][0]["label"] == "unclassified"
    assert data["excluded"][0]["reason"] == "Not yet classified."
