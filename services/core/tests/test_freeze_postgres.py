"""6.9: a lien opens one freeze case, stamped at the lien, and WF20 hears about it once."""

from datetime import datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.rails import freeze
from test_payments_postgres import api, read, request  # noqa: F401  (api is a fixture)


pytestmark = pytest.mark.postgres

LIEN_AT = "2026-03-24T09:30:00+05:30"


@pytest.fixture
def webhooks(monkeypatch):
    sent = []
    monkeypatch.setattr(freeze, "notify", sent.append)
    return sent


def lien(profile, *, ts=LIEN_AT, event_id=None):
    return {"event_id": event_id or f"E-{uuid4().hex}", "type": "lien_marked", "merchant_id": profile["merchant_id"],
            "ts": ts, "freeze_type": "debit_freeze", "scope": "entire account",
            "authority": {"unit": "Cyber Crime Police Station, Hyderabad", "state": "Telangana", "city": "Hyderabad"},
            "ncrp_ack": "SYN-31703260045812", "case_ref": "SYN Cr. No. 412/2026", "disputed_amount": 4200,
            "disputed_date": "2026-03-21", "disputed_utr": "608019038619",
            "intimation": "Lien marked by the bank on a law-enforcement request."}


def decline(profile, minutes_from_lien):
    ts = datetime.fromisoformat(LIEN_AT) + timedelta(minutes=minutes_from_lien)
    return {"event_id": f"E-{uuid4().hex}", "type": "payment_declined", "merchant_id": profile["merchant_id"],
            "ts": ts.isoformat(), "direction": "DR", "amount": 29690, "channel": "UPI_OUT",
            "reason_code": "SYN-DEBIT-FREEZE", "reason": "Debit not allowed", "purpose": "supplier payment",
            "counterparty_id": "PF1", "counterparty_name": "NAIK AGRO TRADERS", "counterparty_handle": "naik@okaxis"}


def send(client, events, sim_at="2026-03-24T10:00:00+05:30"):
    request(client, "/sim/clock", {"sim_at": sim_at}, "admin").raise_for_status()
    response = request(client, "/rails/events", {"events": events, "sim_at": sim_at}, "rails")
    assert response.status_code == 200, response.text
    return response.json()


def cases(connection, profile):
    return connection.execute(text("SELECT * FROM ops.cases WHERE merchant_id = :m ORDER BY opened_at"),
                              {"m": profile["merchant_id"]}).mappings().all()


def opened_entries(client, profile):
    entries = read(client, f"/ledger/{profile['merchant_id']}/entries", role="officer", limit=200).json()["entries"]
    return [entry for entry in entries if entry["kind"] == "case.opened"]


def test_a_lien_opens_one_freeze_case_at_the_lien_time_and_tells_wf20(api, webhooks):
    client, connection, profile = api
    event = lien(profile)
    # Ingested half an hour after the lien: the case must still be dated to the lien itself.
    result = send(client, [event], sim_at="2026-03-24T10:00:00+05:30")
    case_id = f"CASE-FREEZE-{event['event_id']}"
    assert result == {"accepted": 1, "opened_case_ids": [case_id]}

    [entry] = opened_entries(client, profile)
    assert entry["payload"] == {"case_id": case_id, "case_type": "freeze", "trigger_ref": event["event_id"]}
    assert entry["actor_role"] == "rails"
    assert datetime.fromisoformat(entry["sim_at"].replace("Z", "+00:00")) == datetime.fromisoformat(LIEN_AT)

    [case] = cases(connection, profile)
    assert case["status"] == "open" and case["case_type"] == "freeze"
    assert case["data"]["lien"]["disputed_utr"] == "608019038619"
    assert case["data"]["decline_burst"] is None

    assert webhooks == [{"case_id": case_id, "merchant_id": profile["merchant_id"],
                         "opened_at": datetime.fromisoformat(LIEN_AT).isoformat(),
                         "trigger": {"event_id": event["event_id"], "type": "lien_marked",
                                     "case_ref": "SYN Cr. No. 412/2026", "disputed_amount": 4200,
                                     "disputed_utr": "608019038619", "decline_burst": None}}]
    assert read(client, "/ledger/verify", profile["merchant_id"], role="officer").json()["ok"]


def test_replaying_the_same_lien_opens_nothing_new_and_stays_quiet(api, webhooks):
    client, connection, profile = api
    event = lien(profile)
    send(client, [event])
    assert send(client, [event]) == {"accepted": 0, "opened_case_ids": []}
    assert len(cases(connection, profile)) == 1
    assert len(opened_entries(client, profile)) == 1
    assert len(webhooks) == 1


def test_a_burst_before_the_lien_is_recorded_whatever_order_the_batch_arrives_in(api, webhooks):
    client, connection, profile = api
    # Listed lien first: the burst is read back from the table, so the batch must be stored in
    # business-time order or these declines would not be there yet when the lien is judged.
    burst = [decline(profile, minutes) for minutes in (-25, -12, -3)]
    event = lien(profile)
    send(client, [event, *burst])
    [case] = cases(connection, profile)
    recorded = case["data"]["decline_burst"]
    assert recorded["count"] == 3
    assert recorded["event_ids"] == [item["event_id"] for item in burst]
    assert webhooks[0]["trigger"]["decline_burst"]["count"] == 3


@pytest.mark.parametrize("minutes", [(-25, -12), (-45, -35, -31), (5, 11, 20)],
                         ids=["two is not a burst", "outside the 30 minutes", "after the lien"])
def test_declines_that_do_not_make_a_burst_before_the_lien_are_not_recorded_as_one(api, webhooks, minutes):
    client, connection, profile = api
    send(client, [lien(profile), *[decline(profile, minute) for minute in minutes]],
         sim_at="2026-03-24T10:00:00+05:30")
    [case] = cases(connection, profile)
    assert case["data"]["decline_burst"] is None


def test_a_late_lien_does_not_count_the_declines_it_caused_as_a_burst_before_it(api, webhooks):
    client, connection, profile = api
    # The bank's lien notice can arrive after the declines it caused have already streamed in.
    # Those declines are the freeze's consequence, not its warning, and must not be read as one.
    send(client, [decline(profile, minutes) for minutes in (5, 11, 20)])
    send(client, [lien(profile)])
    [case] = cases(connection, profile)
    assert case["data"]["decline_burst"] is None


def test_opening_the_same_case_twice_appends_one_entry(api, webhooks):
    client, connection, profile = api
    # Reached today only if the events table's own dedup were bypassed, and once 6.8 wires
    # POST /cases to this helper, by any second caller naming the same case. The chain refuses
    # deletes, so a second case.opened could never be taken back.
    arguments = dict(merchant_id=profile["merchant_id"], case_type="freeze", trigger_ref="E-1",
                     sim_at=datetime.fromisoformat(LIEN_AT), actor_role="rails", actor_ref="test",
                     case_id="CASE-FREEZE-E-1")
    first = freeze.open_case(connection, **arguments)
    second = freeze.open_case(connection, **arguments)
    assert first[1] is not None and second == ("CASE-FREEZE-E-1", None)
    assert len(opened_entries(client, profile)) == 1


def test_declines_without_a_lien_open_no_case(api, webhooks):
    client, connection, profile = api
    # An outage looks the same from here; telling a merchant their money is held when it is not
    # would be the worst false alarm this product can raise.
    result = send(client, [decline(profile, minutes) for minutes in (-20, -10, -5, -1)])
    assert result == {"accepted": 4, "opened_case_ids": []}
    assert cases(connection, profile) == []
    assert webhooks == []


def test_a_rejected_batch_opens_no_case_and_sends_no_webhook(api, webhooks):
    client, connection, profile = api
    future = lien(profile, ts="2026-03-24T11:00:00+05:30")
    request(client, "/sim/clock", {"sim_at": "2026-03-24T10:00:00+05:30"}, "admin").raise_for_status()
    response = request(client, "/rails/events", {"events": [lien(profile), future], "sim_at": "2026-03-24T10:00:00+05:30"}, "rails")
    assert response.status_code == 422
    assert cases(connection, profile) == []
    assert webhooks == []


def test_only_rails_may_report_a_lien(api, webhooks):
    client, connection, profile = api
    for role in ("evidence", "officer", "provenance", "app"):
        response = request(client, "/rails/events", {"events": [lien(profile)], "sim_at": LIEN_AT}, role)
        assert response.status_code == 403, (role, response.text)
    assert cases(connection, profile) == []
