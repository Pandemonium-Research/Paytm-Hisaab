"""Threshold verdict, crossing date, and trailing-60-day projection."""

from datetime import date, timedelta

import pytest

from test_payments_postgres import api, payment, propose, request  # noqa: F401
from test_stubs import NOW


pytestmark = pytest.mark.postgres

PERIOD_FROM = "2025-04-01"
PERIOD_TO = "2026-03-31"
AS_OF = NOW


def threshold_body(profile, **extra):
    return {
        "merchant_id": profile["merchant_id"],
        "period_from": PERIOD_FROM,
        "period_to": PERIOD_TO,
        "as_of": AS_OF,
        "supply_kind": "goods",
        "gst_status": "unregistered",
        "aggregate_turnover": 0,
        "exclusively_exempt": False,
        **extra,
    }


def call_threshold(client, profile, **extra):
    response = request(client, "/skills/threshold", threshold_body(profile, **extra), "evidence")
    assert response.status_code == 200, response.text
    return response.json()


def sale(client, profile, amount, ts):
    value = payment(client, profile, amount=amount, ts=ts)
    propose(client, value, "taxable_supply")
    return value


def test_goods_and_services_thresholds(api):
    client, _connection, profile = api
    goods = call_threshold(client, profile, supply_kind="goods", aggregate_turnover=1)
    services = call_threshold(client, profile, supply_kind="services", aggregate_turnover=1)
    assert goods["threshold"] == 4_000_000
    assert services["threshold"] == 2_000_000


def test_strictly_above_for_registration(api):
    client, _connection, profile = api
    at_limit = call_threshold(
        client, profile, supply_kind="goods", aggregate_turnover=4_000_000,
    )
    one_rupee_over = call_threshold(
        client, profile, supply_kind="goods", aggregate_turnover=4_000_001,
    )
    assert at_limit["registration_required"] is False
    assert one_rupee_over["registration_required"] is True


def test_crossed_on_is_first_business_day_running_total_strictly_crosses(api):
    client, _connection, profile = api
    day_one = "2026-03-01T10:00:00+05:30"
    day_two = "2026-03-02T10:00:00+05:30"
    sale(client, profile, 2_000_000, day_one)
    sale(client, profile, 2_000_001, day_two)

    data = call_threshold(
        client,
        profile,
        period_from="2026-03-01",
        period_to="2026-03-31",
        aggregate_turnover=4_000_001,
    )
    assert data["crossed_on"] == "2026-03-02"
    assert data["crossed_on"] != "2026-03-01"


def test_exclusively_exempt_cites_section_23_even_above_threshold(api):
    client, _connection, profile = api
    data = call_threshold(
        client,
        profile,
        exclusively_exempt=True,
        aggregate_turnover=5_000_000,
    )
    assert data["registration_required"] is False
    assert "s.23" in data["reason"]


def test_registered_and_composition_skip_registration_check(api):
    client, _connection, profile = api
    for status in ("registered", "composition", "Registered", "COMPOSITION"):
        data = call_threshold(
            client,
            profile,
            gst_status=status,
            aggregate_turnover=5_000_000,
        )
        assert data["registration_required"] is False
        assert "return-mismatch" in data["reason"].casefold()


def test_projection_uses_trailing_sixty_days_and_ceil(api):
    client, _connection, profile = api
    as_of_day = date.fromisoformat("2026-03-24")
    for offset in range(10):
        day = as_of_day - timedelta(days=offset)
        sale(
            client,
            profile,
            60_000,
            # Before NOW's 09:30, so the last day's sale is not observed ahead of the clock.
            f"{day.isoformat()}T09:00:00+05:30",
        )
    data = call_threshold(
        client,
        profile,
        aggregate_turnover=3_900_000,
    )
    assert data["crossed_on"] is None
    assert data["trailing_60_day_run_rate"] == 600_000
    assert data["projected_crossing_on"] == "2026-04-03"
    assert data["warning_days"] == 10


def test_zero_trailing_rate_yields_no_projection(api):
    client, _connection, profile = api
    data = call_threshold(
        client,
        profile,
        aggregate_turnover=100_000,
    )
    assert data["crossed_on"] is None
    assert data["trailing_60_day_run_rate"] == 0
    assert data["projected_crossing_on"] is None
    assert data["warning_days"] is None


def test_above_threshold_suppresses_projection_fields(api):
    client, _connection, profile = api
    as_of_day = date.fromisoformat(AS_OF[:10])
    for offset in range(10):
        day = as_of_day - timedelta(days=offset)
        sale(
            client,
            profile,
            60_000,
            f"{day.isoformat()}T09:00:00+05:30",
        )
    for aggregate in (4_100_000, 4_000_001):
        data = call_threshold(client, profile, aggregate_turnover=aggregate)
        assert data["registration_required"] is True
        assert data["crossed_on"] is None
        assert data["projected_crossing_on"] is None
        assert data["trailing_60_day_run_rate"] is None
        assert data["warning_days"] is None
        for field in ("projected_crossing_on", "crossed_on"):
            value = data.get(field)
            if value is not None:
                assert date.fromisoformat(value) >= as_of_day


def test_registered_suppresses_projection_fields(api):
    client, _connection, profile = api
    as_of_day = date.fromisoformat(AS_OF[:10])
    for offset in range(10):
        day = as_of_day - timedelta(days=offset)
        sale(
            client,
            profile,
            60_000,
            f"{day.isoformat()}T09:00:00+05:30",
        )
    data = call_threshold(
        client,
        profile,
        gst_status="registered",
        aggregate_turnover=3_900_000,
    )
    assert data["projected_crossing_on"] is None
    assert data["trailing_60_day_run_rate"] is None
    assert data["warning_days"] is None


def test_exclusively_exempt_suppresses_projection_fields(api):
    client, _connection, profile = api
    as_of_day = date.fromisoformat(AS_OF[:10])
    for offset in range(10):
        day = as_of_day - timedelta(days=offset)
        sale(
            client,
            profile,
            60_000,
            f"{day.isoformat()}T09:00:00+05:30",
        )
    data = call_threshold(
        client,
        profile,
        exclusively_exempt=True,
        aggregate_turnover=3_900_000,
    )
    assert data["projected_crossing_on"] is None
    assert data["trailing_60_day_run_rate"] is None
    assert data["warning_days"] is None


def test_crossed_clears_projection_fields(api):
    client, _connection, profile = api
    sale(client, profile, 4_000_001, "2026-03-10T10:00:00+05:30")
    data = call_threshold(
        client,
        profile,
        period_from="2026-03-01",
        period_to="2026-03-31",
        aggregate_turnover=4_000_001,
    )
    assert data["crossed_on"] == "2026-03-10"
    assert data["projected_crossing_on"] is None
    assert data["trailing_60_day_run_rate"] is None
    assert data["warning_days"] is None
