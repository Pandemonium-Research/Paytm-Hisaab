"""Evidence tiers are computed from visible ledger history relative to the case boundary."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from test_payments_postgres import api, payment, request  # noqa: F401  (api is a fixture)
from test_stubs import NOW


pytestmark = pytest.mark.postgres

OPENED_AT = "2026-03-23T12:00:00+05:30"
BEFORE = "2026-03-22T10:00:00+05:30"


def open_case(connection, profile, *, opened_at=OPENED_AT):
    case_id = f"CASE-TIERS-{uuid4().hex}"
    connection.execute(
        text("""INSERT INTO ops.cases
                (case_id, merchant_id, case_type, trigger_ref, opened_at)
                VALUES (:case, :merchant, 'freeze', :trigger, :opened_at)"""),
        {"case": case_id, "merchant": profile["merchant_id"],
         "trigger": f"E-{uuid4().hex}", "opened_at": opened_at},
    )
    return case_id


def propose_at(client, value, sim_at, label="taxable_supply"):
    response = request(
        client,
        "/ledger/proposals",
        {"merchant_id": value["merchant_id"], "txn_id": value["txn_id"], "sim_at": sim_at,
         "proposal": {"label": label, "source": "rule", "rule_id": "tiers-test",
                      "confidence": 0.9, "reason": "Test evidence tier."}},
        "provenance",
    )
    assert response.status_code == 200, response.text


def answer_at(client, value, sim_at):
    question_id = f"Q-{uuid4().hex}"
    asked_at = datetime.fromisoformat(sim_at) - timedelta(minutes=1)
    response = request(
        client,
        "/ledger/questions",
        {"merchant_id": value["merchant_id"], "txn_id": value["txn_id"],
         "sim_at": asked_at.isoformat(),
         "question": {"question_id": question_id, "text": "What was this payment for?",
                      "language": "en", "expires_at": (asked_at + timedelta(days=7)).isoformat()}},
        "conversation",
    )
    assert response.status_code == 200, response.text
    response = request(
        client,
        "/ledger/claims",
        {"merchant_id": value["merchant_id"], "txn_id": value["txn_id"], "action": "answered",
         "sim_at": sim_at, "claim": {"question_id": question_id, "answer": "family",
                                        "raw_text": "Family", "language": "en"}},
        "conversation",
    )
    assert response.status_code == 200, response.text


def annotate_at(client, value, sim_at):
    response = request(
        client,
        "/ledger/claims",
        {"merchant_id": value["merchant_id"], "txn_id": value["txn_id"], "action": "annotated",
         "sim_at": sim_at, "claim": {"label": "personal_transfer",
                                        "raw_text": "Personal transfer", "language": "en"}},
        "conversation",
    )
    assert response.status_code == 200, response.text


def linked_bill(client, connection, profile, amount):
    bill_id = f"B-{uuid4().hex}"
    item = f"Test item {uuid4().hex}"
    value = payment(client, profile, amount=amount, bill=bill_id,
                    channel="UPI_POS", ts="2026-03-21T00:30:00+05:30")
    connection.execute(
        text("INSERT INTO rails.hsn_catalog (item, hsn, exempt) VALUES (:item, '9999', false)"),
        {"item": item},
    )
    response = request(
        client,
        "/rails/bills",
        {"sim_at": BEFORE, "lines": [{"pos_bill_id": bill_id, "txn_id": value["txn_id"],
         "merchant_id": profile["merchant_id"], "line_no": 1, "item": item, "hsn": "9999",
         "qty": "1", "unit": "item", "rate": str(amount), "line_amount": amount}]},
        "rails",
    )
    assert response.status_code == 200, response.text
    propose_at(client, value, BEFORE)
    return value


def tiers_body(profile, case_id, **extra):
    return {
        "merchant_id": profile["merchant_id"],
        "case_id": case_id,
        "opened_at": OPENED_AT,
        "period_from": "2026-03-21",
        "period_to": "2026-03-21",
        "as_of": NOW,
        **extra,
    }


def test_tiers_aggregate_all_evidence_and_filter_by_business_day(api):
    client, connection, profile = api
    case_id = open_case(connection, profile)

    linked_bill(client, connection, profile, 100)
    rule = payment(client, profile, amount=200, ts="2026-03-20T19:00:00Z")
    propose_at(client, rule, BEFORE)
    answered = payment(client, profile, amount=300, ts="2026-03-21T10:00:00+05:30")
    answer_at(client, answered, BEFORE)
    annotated = payment(client, profile, amount=400, ts="2026-03-21T11:00:00+05:30")
    annotate_at(client, annotated, BEFORE)
    outside = payment(client, profile, amount=500, ts="2026-03-20T18:00:00Z")
    propose_at(client, outside, BEFORE)

    response = request(client, "/skills/tiers", tiers_body(profile, case_id), "evidence")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "totals": [
            {"tier": 1, "amount": 100, "count": 1},
            {"tier": 2, "amount": 200, "count": 1},
            {"tier": 3, "amount": 300, "count": 1},
            {"tier": 4, "amount": 400, "count": 1},
        ],
        "strong_shape_fraction": 0.3,
    }


def test_entries_crossing_the_case_boundary_become_tier_four(api):
    client, connection, profile = api
    instants = {
        "before": "2026-03-23T11:59:59+05:30",
        "at": OPENED_AT,
        "after": "2026-03-23T12:00:01+05:30",
    }
    values = {}
    for name, sim_at in instants.items():
        values[name] = payment(client, profile, ts="2026-03-21T10:00:00+05:30")
        propose_at(client, values[name], sim_at)

    rows = connection.execute(
        text("""SELECT txn_id, tier FROM ledger.current_view(:merchant, :as_of, :opened_at)
                WHERE txn_id = ANY(:txns)"""),
        {"merchant": profile["merchant_id"], "as_of": NOW, "opened_at": OPENED_AT,
         "txns": [value["txn_id"] for value in values.values()]},
    ).mappings().all()
    found = {row["txn_id"]: row["tier"] for row in rows}
    assert found[values["before"]["txn_id"]] == 2
    assert found[values["at"]["txn_id"]] == 4
    assert found[values["after"]["txn_id"]] == 4


def test_empty_period_returns_all_tiers_and_zero_shape(api):
    client, connection, profile = api
    case_id = open_case(connection, profile)
    response = request(client, "/skills/tiers", tiers_body(profile, case_id), "evidence")
    assert response.status_code == 200, response.text
    assert response.json() == {
        "totals": [
            {"tier": 1, "amount": 0, "count": 0},
            {"tier": 2, "amount": 0, "count": 0},
            {"tier": 3, "amount": 0, "count": 0},
            {"tier": 4, "amount": 0, "count": 0},
        ],
        "strong_shape_fraction": 0.0,
    }


def test_tiers_rejects_a_case_for_another_merchant_or_after_as_of(api):
    client, connection, profile = api
    case_id = open_case(connection, profile)
    wrong = request(
        client,
        "/skills/tiers",
        tiers_body(profile, case_id, merchant_id=f"wrong-{uuid4().hex}"),
        "evidence",
    )
    assert wrong.status_code == 404
    assert wrong.json()["detail"] == f"No case {case_id} for this merchant at that time."

    future = "2026-03-25T12:00:00+05:30"
    future_case = open_case(connection, profile, opened_at=future)
    hidden = request(
        client,
        "/skills/tiers",
        tiers_body(profile, future_case, opened_at=future),
        "evidence",
    )
    assert hidden.status_code == 404
    assert hidden.json()["detail"] == f"No case {future_case} for this merchant at that time."
