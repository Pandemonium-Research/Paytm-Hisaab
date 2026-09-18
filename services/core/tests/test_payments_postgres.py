"""Functional HTTP loop against Postgres, with each test rolled back."""

import csv
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.db import get_connection, sqlalchemy_url
from app.main import app
from test_stubs import NOW, TRANSACTION


pytestmark = pytest.mark.postgres


@pytest.fixture
def api():
    url = os.getenv("TEST_DATABASE_URL")
    if not url:
        pytest.skip("run python tasks.py test --postgres")
    assert make_url(url).database == "hisaab_ledger_test"
    engine = create_engine(sqlalchemy_url(url))
    with engine.connect() as connection:
        transaction = connection.begin()
        def dependency():
            with connection.begin_nested():
                yield connection
        app.dependency_overrides[get_connection] = dependency
        profile = json.loads((Path(__file__).parents[1] / "app/fixtures/reads.json").read_text())["GET /merchants/{id}"]
        profile.update(merchant_id=f"test-{uuid4().hex}", owner_name="SAHANA GOWDA")
        connection.execute(text("INSERT INTO rails.merchants (merchant_id, profile) VALUES (:merchant, CAST(:profile AS jsonb))"), {"merchant": profile["merchant_id"], "profile": json.dumps(profile)})
        with TestClient(app) as client:
            client.post("/sim/clock", headers={"X-Hisaab-Key": "dev-admin"}, json={"sim_at": NOW}).raise_for_status()
            yield client, connection, profile
        app.dependency_overrides.clear()
        transaction.rollback()
    engine.dispose()


def request(client, path, body, role):
    return client.post(path, headers={"X-Hisaab-Key": f"dev-{role}"}, json=body)


def payment(client, profile, *, amount=4200, payer="P123", ts="2026-03-21T19:47:00+05:30", channel="UPI_QR", bill=None, handle="payer@upi", name="DEMO CUSTOMER"):
    identifier = uuid4().hex
    value = {**TRANSACTION, "txn_id": f"T-{identifier}", "merchant_id": profile["merchant_id"],
        "amount": amount, "ts": ts, "channel": channel, "pos_bill_id": bill,
        "utr": str(int(identifier[:10], 16) % 10**12).zfill(12), "counterparty_id": payer,
        "counterparty_handle": handle, "counterparty_name": name}
    response = request(client, "/rails/credits", {"transactions": [value], "sim_at": NOW}, "rails")
    assert response.status_code == 200, response.text
    return value


def propose(client, value, label="taxable_supply"):
    body = {"merchant_id": value["merchant_id"], "txn_id": value["txn_id"], "sim_at": NOW,
        "proposal": {"label": label, "source": "rule", "rule_id": "test", "confidence": 0.9, "reason": "Test observable rule."}}
    response = request(client, "/ledger/proposals", body, "provenance")
    assert response.status_code == 200, response.text
    return response.json()["entry"]


def ask(client, value):
    body = {"merchant_id": value["merchant_id"], "txn_id": value["txn_id"], "sim_at": NOW,
        "question": {"question_id": f"Q-{uuid4().hex}", "text": "What was this payment for?", "language": "kn-IN",
                     "expires_at": (datetime.fromisoformat(NOW) + timedelta(days=7)).isoformat()}}
    response = request(client, "/ledger/questions", body, "conversation")
    assert response.status_code == 200, response.text
    return body, response.json()["entry"]


def read(client, path, merchant=None, role="app", **params):
    if merchant:
        params["merchant"] = merchant
    return client.get(path, params=params, headers={"X-Hisaab-Key": f"dev-{role}"})


def test_ingest_is_idempotent_and_conflicting_retries_cannot_overwrite(api):
    client, connection, profile = api
    value = payment(client, profile)
    response = request(client, "/rails/credits", {"transactions": [value], "sim_at": NOW}, "rails")
    assert response.json() == {"accepted": 0, "duplicate_txn_ids": [value["txn_id"]]}
    response = request(client, "/rails/credits", {"transactions": [{**value, "amount": 4201}], "sim_at": NOW}, "rails")
    assert response.status_code == 409
    assert read(client, f"/credits/{value['txn_id']}", role="provenance").json()["transaction"]["amount"] == 4200
    assert read(client, "/ledger/verify", profile["merchant_id"], role="admin").json()["ok"]


@pytest.mark.parametrize("answer, expected, fact", [("family", "personal_transfer", True), ("not_sure", "taxable_supply", False)])
def test_answer_persists_without_removing_machine_label_and_closes_question(api, answer, expected, fact):
    client, connection, profile = api
    value = payment(client, profile)
    machine = propose(client, value)
    body, question = ask(client, value)
    assert len(bytes.fromhex(machine["hash"])) == 32
    assert read(client, "/app/home", profile["merchant_id"]).json()["questions_due"] == 1
    cards = read(client, "/app/questions", profile["merchant_id"]).json()["items"]
    assert cards[0]["question_id"] == body["question"]["question_id"]
    claim = {"merchant_id": profile["merchant_id"], "txn_id": value["txn_id"], "action": "answered", "sim_at": NOW,
        "claim": {"question_id": body["question"]["question_id"], "answer": answer, "raw_text": "2" if fact else "4", "language": "kn-IN"}}
    response = request(client, "/ledger/claims", claim, "conversation")
    assert response.status_code == 200, response.text
    assert response.json()["payer_fact_updated"] is fact
    retry = request(client, "/ledger/claims", claim, "conversation")
    assert retry.json()["entry"]["seq"] == response.json()["entry"]["seq"]
    current = read(client, f"/credits/{value['txn_id']}", role="provenance").json()
    assert current["machine_label"] == "taxable_supply" and current["effective_label"] == expected
    assert current["claim_label"] == (expected if fact else None)
    assert machine["seq"] in current["entry_refs"]
    assert read(client, "/app/questions", profile["merchant_id"]).json()["items"] == []
    assert read(client, "/app/home", profile["merchant_id"]).json()["questions_due"] == 0
    later = (datetime.fromisoformat(NOW) + timedelta(seconds=1)).isoformat()
    history = read(client, f"/payers/{value['counterparty_id']}/history", profile["merchant_id"], role="provenance", as_of=later).json()
    assert bool(history["payer_facts"]) is fact
    assert read(client, "/ledger/verify", profile["merchant_id"], role="admin").json()["ok"]


def test_pagination_and_business_time_hide_future_rows_and_answers(api):
    client, connection, profile = api
    values = [payment(client, profile, ts=f"2026-03-{day}T10:00:00+05:30") for day in (20, 21, 22)]
    first = read(client, "/credits", profile["merchant_id"], role="provenance", limit=1).json()
    second = read(client, "/credits", profile["merchant_id"], role="provenance", limit=1, cursor=first["next_cursor"]).json()
    assert first["items"][0]["transaction"]["txn_id"] != second["items"][0]["transaction"]["txn_id"]
    request(client, "/sim/clock", {"sim_at": "2026-03-21T00:00:00+05:30"}, "admin").raise_for_status()
    rows = read(client, "/credits", profile["merchant_id"], role="provenance").json()["items"]
    assert [row["transaction"]["txn_id"] for row in rows] == [values[0]["txn_id"]]
    assert read(client, f"/credits/{values[2]['txn_id']}", role="provenance").status_code == 404
    history = read(client, "/payers/P123/history", profile["merchant_id"], role="provenance", as_of=values[1]["ts"]).json()
    assert history["strictly_prior_credit_count"] == 1


def test_credit_window_is_half_open_and_reads_the_same_instant_in_either_zone(api):
    client, connection, profile = api
    days = {day: payment(client, profile, ts=f"2026-03-{day}T10:00:00+05:30") for day in (20, 21, 22)}

    def window(start, end, **extra):
        response = read(client, "/credits", profile["merchant_id"], role="provenance",
                        **{"from": start, "to": end}, **extra)
        assert response.status_code == 200, response.text
        return response.json()

    # from is inclusive and to is exclusive, so the payment exactly at the end is left out.
    inside = window("2026-03-21T10:00:00+05:30", "2026-03-22T10:00:00+05:30")
    assert [row["transaction"]["txn_id"] for row in inside["items"]] == [days[21]["txn_id"]]

    # The chain stores UTC and the screens speak IST. The same instant written either way
    # must select the same payments; this is the comparison that has already bitten us once.
    assert window("2026-03-21T04:30:00Z", "2026-03-22T04:30:00Z")["items"] == inside["items"]

    # A window still pages, and the cursor stays inside it.
    first = window("2026-03-20T00:00:00+05:30", "2026-03-22T00:00:00+05:30", limit=1)
    second = window("2026-03-20T00:00:00+05:30", "2026-03-22T00:00:00+05:30", limit=1, cursor=first["next_cursor"])
    assert [first["items"][0]["transaction"]["txn_id"], second["items"][0]["transaction"]["txn_id"]] == \
        [days[20]["txn_id"], days[21]["txn_id"]]
    assert second["next_cursor"] is None

    # A window cannot outrun business time even when it asks to.
    request(client, "/sim/clock", {"sim_at": "2026-03-21T00:00:00+05:30"}, "admin").raise_for_status()
    assert [row["transaction"]["txn_id"] for row in
            window("2026-03-19T00:00:00+05:30", "2026-03-25T00:00:00+05:30")["items"]] == [days[20]["txn_id"]]

    # An empty or unzoned window is a caller mistake, not an empty page.
    assert read(client, "/credits", profile["merchant_id"], role="provenance",
                **{"from": "2026-03-22T00:00:00+05:30", "to": "2026-03-21T00:00:00+05:30"}).status_code == 422
    assert read(client, "/credits", profile["merchant_id"], role="provenance",
                **{"from": "2026-03-21T00:00:00"}).status_code == 422


def test_question_budget_is_enforced_at_write_and_retries_do_not_spend_twice(api):
    client, connection, profile = api
    value = payment(client, profile)
    body, first = ask(client, value)
    assert request(client, "/ledger/questions", body, "conversation").json()["entry"]["seq"] == first["seq"]
    ask(client, value)
    third_body, _ = ask(client, value)
    third_body["question"]["question_id"] = f"Q-{uuid4().hex}"
    assert request(client, "/ledger/questions", third_body, "conversation").status_code == 409
    future = {"merchant_id": profile["merchant_id"], "txn_id": value["txn_id"], "sim_at": "2026-09-18T17:00:00+05:30",
        "proposal": {"label": "taxable_supply", "source": "rule", "rule_id": "test", "confidence": 1.0, "reason": "Future."}}
    assert request(client, "/ledger/proposals", future, "provenance").status_code == 422


def test_bill_and_claim_are_independent_and_conflict_is_visible(api):
    client, connection, profile = api
    bill_id = f"B-{uuid4().hex}"
    value = payment(client, profile, channel="UPI_POS", bill=bill_id)
    connection.execute(text("INSERT INTO rails.hsn_catalog (item, hsn, exempt) VALUES ('Test onions', '0703', true) ON CONFLICT DO NOTHING"))
    line = {"pos_bill_id": bill_id, "txn_id": value["txn_id"], "merchant_id": profile["merchant_id"],
        "line_no": 1, "item": "Test onions", "hsn": "0703", "qty": "1", "unit": "kg", "rate": "4200", "line_amount": 4200}
    bill = request(client, "/rails/bills", {"lines": [line], "sim_at": NOW}, "rails")
    assert bill.status_code == 200, bill.text
    assert request(client, "/rails/bills", {"lines": [line], "sim_at": NOW}, "rails").json()["accepted_lines"] == 0
    propose(client, value, "exempt_supply")
    body, _ = ask(client, value)
    response = request(client, "/ledger/claims", {"merchant_id": profile["merchant_id"], "txn_id": value["txn_id"],
        "action": "answered", "sim_at": NOW, "claim": {"question_id": body["question"]["question_id"], "answer": "family", "raw_text": "Family", "language": "kn-IN"}}, "conversation")
    assert response.status_code == 200, response.text
    detail = read(client, f"/app/payments/{value['txn_id']}", profile["merchant_id"]).json()
    assert detail["machine_label"] == "exempt_supply" and detail["claim_label"] == "personal_transfer" and detail["conflict"]


def test_real_rules_and_selection_choose_three_questions_and_ignore_tiny_credit(api):
    client, connection, profile = api
    for day in (10, 11, 12, 13):
        payment(client, profile, amount=250, payer="SPOUSE", name="K GOWDA", ts=f"2026-03-{day}T10:00:00+05:30")
    own = payment(client, profile, amount=15000, channel="IMPS", handle=profile["linked_own_accounts"][0])
    spouse = payment(client, profile, amount=7500, payer="SPOUSE", name="K GOWDA")
    repeat = payment(client, profile, amount=4850, payer="REPEAT")
    tiny = payment(client, profile, amount=23, payer="TINY", channel="IMPS")
    values = [own, spouse, repeat, tiny]
    features = [{"txn_id": value["txn_id"], "amount": value["amount"], "channel": value["channel"],
        "counterparty_id": value["counterparty_id"], "counterparty_name": value["counterparty_name"],
        "has_bill": False, "prior_credit_count": 0, "merchant_has_paid_them": False,
        "own_account_cue": False, "surname_cue": False} for value in values]
    classifications = request(client, "/skills/classify-rules", {"merchant_id": profile["merchant_id"], "as_of": NOW, "credits": features}, "provenance")
    assert classifications.status_code == 200, classifications.text
    predictions = {item["txn_id"]: item["result"] for item in classifications.json()["results"]}
    assert predictions[spouse["txn_id"]]["ask"]
    assert predictions[spouse["txn_id"]]["confidence"] < 0.75
    candidates = [{"txn_id": value["txn_id"], "payer_id": value["counterparty_id"], "amount": value["amount"],
        "label": (predictions[value["txn_id"]] or {}).get("label"), "confidence": (predictions[value["txn_id"]] or {}).get("confidence", 0),
        "strictly_prior_credit_count": 0, "has_bill": False, "payer_fact_known": False, "proposed_at": NOW} for value in values]
    selected = request(client, "/skills/select-questions", {"merchant_id": profile["merchant_id"], "as_of": NOW, "candidates": candidates,
        "projected_turnover": 3900000, "threshold": 4000000}, "provenance")
    assert selected.status_code == 200, selected.text
    assert {item["txn_id"] for item in selected.json()["selected"]} == {own["txn_id"], spouse["txn_id"], repeat["txn_id"]}
    assert selected.json()["remaining_daily_budget"] == 0


def test_replay_loads_only_visible_rows_to_cutoff_and_is_repeatable(api, tmp_path, monkeypatch):
    client, connection, profile = api
    visible = tmp_path / "demo" / "visible"
    visible.mkdir(parents=True)
    (visible / "merchants.json").write_text(json.dumps([profile]))
    (visible / "terminals.json").write_text("[]")
    (visible / "rails_events.json").write_text("[]")
    (visible / "hsn_catalog.json").write_text(json.dumps([{"item": "Test", "hsn": "0000", "exempt": False}]))
    with (visible / "transactions.csv").open("w") as handle:
        writer = csv.DictWriter(handle, fieldnames=TRANSACTION.keys())
        writer.writeheader()
        for day in (20, 25):
            writer.writerow({**TRANSACTION, "merchant_id": profile["merchant_id"], "txn_id": f"R-{uuid4().hex}",
                "ts": f"2026-03-{day}T10:00:00+05:30", "channel": "UPI_QR", "pos_bill_id": ""})
    (visible / "pos_bill_lines.csv").write_text("pos_bill_id,txn_id,merchant_id,line_no,item,hsn,qty,unit,rate,line_amount\n")
    monkeypatch.setenv("HISAAB_DATA_DIR", str(tmp_path))
    first = request(client, "/sim/replay", {"split": "demo", "until": NOW}, "admin")
    assert first.status_code == 200, first.text
    assert first.json()["transactions_replayed"] == 1
    assert request(client, "/sim/replay", {"split": "demo", "until": NOW}, "admin").json()["transactions_replayed"] == 0
    assert len(read(client, "/credits", profile["merchant_id"], role="provenance").json()["items"]) == 1


def test_assistant_workflow_acceptance_failure_and_persisted_delivery(api, monkeypatch):
    import urllib.error
    from app.routers import assistant

    client, connection, profile = api
    forwarded = []
    monkeypatch.setattr(assistant, "forward", lambda body: forwarded.append(body.model_dump(mode="json")))
    inbound = {"merchant_id": profile["merchant_id"], "message_id": "app-tap", "content_type": "text",
        "text": '{"type":"question_answer","question_id":"Q-test","txn_id":"T-test","answer":"family"}',
        "language": "kn-IN", "sim_at": NOW}
    response = request(client, "/assistant/inbound", inbound, "app")
    assert response.status_code == 200 and response.json()["forwarded_to_workflow"]
    assert forwarded[0]["text"] == inbound["text"]
    conversation = response.json()["conversation_id"]
    outgoing = {"merchant_id": profile["merchant_id"], "conversation_id": conversation,
        "text": "Saved your answer.", "language": "kn-IN", "in_reply_to": "app-tap", "sim_at": NOW}
    response = request(client, "/assistant/outbound", outgoing, "conversation")
    assert response.status_code == 200 and response.json()["published"]
    stored = connection.execute(text("SELECT data FROM ops.conversations WHERE conversation_id=:id"), {"id": conversation}).scalar_one()
    assert stored["messages"][0]["text"] == outgoing["text"]
    assert stored["messages"][0]["message_id"] == response.json()["message_id"]
    monkeypatch.undo()
    def unavailable(*args, **kwargs):
        raise urllib.error.URLError("local workflow offline")
    monkeypatch.setattr(assistant.urllib.request, "urlopen", unavailable)
    failed = request(client, "/assistant/inbound", inbound, "app")
    assert failed.status_code == 502
