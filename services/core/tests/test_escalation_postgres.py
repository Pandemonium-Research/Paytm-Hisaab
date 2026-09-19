"""Escalation-check routes freeze cases to a specialist when any rule fires."""

from uuid import uuid4

import pytest
from sqlalchemy import text

from test_payments_postgres import api, request  # noqa: F401

pytestmark = pytest.mark.postgres

OPENED_AT = "2026-03-23T12:00:00+05:30"


def open_case(connection, profile):
    case_id = f"CASE-ESC-{uuid4().hex}"
    connection.execute(
        text("""INSERT INTO ops.cases
                (case_id, merchant_id, case_type, trigger_ref, opened_at)
                VALUES (:case, :merchant, 'freeze', :trigger, :opened_at)"""),
        {"case": case_id, "merchant": profile["merchant_id"],
         "trigger": f"E-{uuid4().hex}", "opened_at": OPENED_AT},
    )
    return case_id


def benign_body(case_id, **extra):
    return {
        "case_id": case_id,
        "disputed_amount": 10_000,
        "disputed_tier": 1,
        "effective_label": "taxable_supply",
        "claim_conflicts_with_bill": False,
        "merchant_disputed_label": False,
        "tier_3_4_share": 0.0,
        "prior_freeze_days_ago": None,
        **extra,
    }


def call_escalation(client, body):
    return request(client, "/skills/escalation-check", body, "evidence")


def assert_one_reason(data, substring: str):
    assert data["escalate"] is True
    assert len(data["reasons"]) == 1
    assert substring in data["reasons"][0]


def test_benign_case_does_not_escalate(api):
    client, connection, profile = api
    case_id = open_case(connection, profile)
    response = call_escalation(client, benign_body(case_id))
    assert response.status_code == 200, response.text
    assert response.json() == {"escalate": False, "reasons": []}


def test_rule_disputed_amount_above_small_sum_limit(api):
    client, connection, profile = api
    case_id = open_case(connection, profile)
    response = call_escalation(client, benign_body(case_id, disputed_amount=75_000))
    assert response.status_code == 200, response.text
    assert_one_reason(response.json(), "small-sum limit")


def test_boundary_disputed_amount_at_limit_does_not_escalate(api):
    client, connection, profile = api
    case_id = open_case(connection, profile)
    response = call_escalation(client, benign_body(case_id, disputed_amount=50_000))
    assert response.status_code == 200, response.text
    assert response.json()["escalate"] is False


def test_boundary_disputed_amount_one_rupee_over_escalates(api):
    client, connection, profile = api
    case_id = open_case(connection, profile)
    response = call_escalation(client, benign_body(case_id, disputed_amount=50_001))
    assert response.status_code == 200, response.text
    assert_one_reason(response.json(), "small-sum limit")


def test_rule_weak_disputed_tier(api):
    client, connection, profile = api
    case_id = open_case(connection, profile)
    for tier in (3, 4):
        response = call_escalation(client, benign_body(case_id, disputed_tier=tier))
        assert response.status_code == 200, response.text
        assert_one_reason(response.json(), "not backed by a bill or a rule")


def test_tier_one_and_two_do_not_escalate_on_weak_tier_rule(api):
    client, connection, profile = api
    case_id = open_case(connection, profile)
    for tier in (1, 2):
        response = call_escalation(client, benign_body(case_id, disputed_tier=tier))
        assert response.status_code == 200, response.text
        assert response.json()["escalate"] is False


def test_rule_effective_label_not_ordinary_sale(api):
    client, connection, profile = api
    case_id = open_case(connection, profile)
    for label in ("personal_transfer", "unclassified"):
        response = call_escalation(client, benign_body(case_id, effective_label=label))
        assert response.status_code == 200, response.text
        assert_one_reason(response.json(), "not an ordinary taxable or exempt supply")


def test_ordinary_sale_labels_do_not_escalate_on_label_rule(api):
    client, connection, profile = api
    case_id = open_case(connection, profile)
    for label in ("taxable_supply", "exempt_supply"):
        response = call_escalation(client, benign_body(case_id, effective_label=label))
        assert response.status_code == 200, response.text
        assert response.json()["escalate"] is False


def test_rule_claim_conflicts_with_bill(api):
    client, connection, profile = api
    case_id = open_case(connection, profile)
    response = call_escalation(client, benign_body(case_id, claim_conflicts_with_bill=True))
    assert response.status_code == 200, response.text
    assert_one_reason(response.json(), "conflicts with the bill")


def test_rule_merchant_disputed_label(api):
    client, connection, profile = api
    case_id = open_case(connection, profile)
    response = call_escalation(client, benign_body(case_id, merchant_disputed_label=True))
    assert response.status_code == 200, response.text
    assert_one_reason(response.json(), "disputed the proposed label")


def test_rule_tier_3_4_share_above_threshold(api):
    client, connection, profile = api
    case_id = open_case(connection, profile)
    response = call_escalation(client, benign_body(case_id, tier_3_4_share=0.41))
    assert response.status_code == 200, response.text
    assert_one_reason(response.json(), "above 40%")


def test_boundary_tier_share_at_threshold_does_not_escalate(api):
    client, connection, profile = api
    case_id = open_case(connection, profile)
    response = call_escalation(client, benign_body(case_id, tier_3_4_share=0.40))
    assert response.status_code == 200, response.text
    assert response.json()["escalate"] is False


def test_rule_prior_freeze_within_repeat_window(api):
    client, connection, profile = api
    case_id = open_case(connection, profile)
    response = call_escalation(client, benign_body(case_id, prior_freeze_days_ago=45))
    assert response.status_code == 200, response.text
    assert_one_reason(response.json(), "within the last 90 days")


def test_boundary_prior_freeze_exactly_ninety_days_escalates(api):
    client, connection, profile = api
    case_id = open_case(connection, profile)
    response = call_escalation(client, benign_body(case_id, prior_freeze_days_ago=90))
    assert response.status_code == 200, response.text
    assert_one_reason(response.json(), "within the last 90 days")


def test_boundary_prior_freeze_ninety_one_days_does_not_escalate(api):
    client, connection, profile = api
    case_id = open_case(connection, profile)
    response = call_escalation(client, benign_body(case_id, prior_freeze_days_ago=91))
    assert response.status_code == 200, response.text
    assert response.json()["escalate"] is False


def test_multiple_rules_produce_reasons_in_order(api):
    client, connection, profile = api
    case_id = open_case(connection, profile)
    response = call_escalation(
        client,
        benign_body(
            case_id,
            disputed_amount=60_000,
            disputed_tier=3,
            effective_label="personal_transfer",
            claim_conflicts_with_bill=True,
            merchant_disputed_label=True,
            tier_3_4_share=0.5,
            prior_freeze_days_ago=10,
        ),
    )
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["escalate"] is True
    reasons = data["reasons"]
    assert len(reasons) == 7
    assert "small-sum limit" in reasons[0]
    assert "not backed by a bill or a rule" in reasons[1]
    assert "not an ordinary taxable or exempt supply" in reasons[2]
    assert "conflicts with the bill" in reasons[3]
    assert "disputed the proposed label" in reasons[4]
    assert "above 40%" in reasons[5]
    assert "within the last 90 days" in reasons[6]


def test_unknown_case_id_returns_404(api):
    client, _connection, _profile = api
    missing = f"CASE-MISSING-{uuid4().hex}"
    response = call_escalation(client, benign_body(missing))
    assert response.status_code == 404
    assert response.json()["detail"] == f"No case {missing} was found."
