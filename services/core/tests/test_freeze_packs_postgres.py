"""6.4 / 6.8: real isolation, case creation, pack artifacts and the officer loop."""

import json
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import text
import test_payments_postgres as payment_helpers

from app.cases.artifacts import sha256_bytes
from app.rails import freeze
from test_approvals_postgres import approve, reject, send
from test_freeze_postgres import lien, send as send_events
from test_payments_postgres import NOW, api, ask, payment, propose, read, request  # noqa: F401


pytestmark = pytest.mark.postgres

LIEN_AT = "2026-03-24T09:30:00+05:30"
BUILT = LIEN_AT
DECIDED = "2026-03-24T10:20:00+05:30"
SENT = "2026-03-24T10:25:00+05:30"


@pytest.fixture
def pack_root(tmp_path, monkeypatch):
    monkeypatch.setenv("HISAAB_PACK_DIR", str(tmp_path))
    return tmp_path


@pytest.fixture
def quiet(api, monkeypatch):
    monkeypatch.setattr(freeze, "notify", lambda body: True)


def clock(client, sim_at):
    request(client, "/sim/clock", {"sim_at": sim_at}, "admin").raise_for_status()


def lien_event(profile, **overrides):
    event = lien(profile)
    event.update(overrides)
    return event


def ingest_bill(client, profile, credit, items, *, sim_at=NOW):
    bill_id = credit["pos_bill_id"]
    lines = []
    remaining = credit["amount"]
    for index, (item, amount) in enumerate(items, start=1):
        if index == len(items):
            amount = remaining
        lines.append(
            {
                "pos_bill_id": bill_id,
                "txn_id": credit["txn_id"],
                "merchant_id": profile["merchant_id"],
                "line_no": index,
                "item": item,
                "hsn": "0703",
                "qty": "1",
                "unit": "kg",
                "rate": str(amount),
                "line_amount": amount,
            }
        )
        remaining -= amount
    response = request(client, "/rails/bills", {"lines": lines, "sim_at": sim_at}, "rails")
    assert response.status_code == 200, response.text
    return bill_id


def credit_with_bill(client, profile, *, bill_id=None, bill_sim_at=NOW, bill_items=None, **payment_kwargs):
    bill_id = bill_id or f"B-{uuid4().hex[:8]}"
    credit = payment(client, profile, bill=bill_id, **payment_kwargs)
    if bill_items is not None:
        ingest_bill(client, profile, credit, bill_items, sim_at=bill_sim_at)
    return credit


def terminal(connection, profile, terminal_id, installed_at, **data):
    connection.execute(
        text("""INSERT INTO rails.terminals (merchant_id, terminal_id, installed_at, data)
                VALUES (:merchant, :terminal, :installed, CAST(:data AS jsonb))
                ON CONFLICT (merchant_id, terminal_id) DO UPDATE SET installed_at = excluded.installed_at, data = excluded.data"""),
        {
            "merchant": profile["merchant_id"],
            "terminal": terminal_id,
            "installed": datetime.fromisoformat(installed_at),
            "data": json.dumps({"device_id": data.get("device_id", "DEV01"), "geo": data.get("geo", {"lat": 12.9, "lon": 77.6})}),
        },
    )


def open_case(client, profile, event, *, case_type="freeze", sim_at=LIEN_AT):
    return request(
        client,
        "/cases",
        {
            "merchant_id": profile["merchant_id"],
            "case_type": case_type,
            "trigger_ref": event["event_id"],
            "sim_at": sim_at,
        },
        "evidence",
    )


def isolate(client, profile, case_id, **extra):
    body = {
        "merchant_id": profile["merchant_id"],
        "case_id": case_id,
        "disputed_utr": extra.get("disputed_utr"),
        "disputed_amount": extra.get("disputed_amount", 4200),
        "disputed_date": extra.get("disputed_date", "2026-03-21"),
        "date_window_days": extra.get("date_window_days", 1),
        "as_of": extra.get("as_of", LIEN_AT),
    }
    return request(client, "/skills/isolate", body, "evidence")


def build(client, profile, case_id, *, sim_at=BUILT, pack_type="freeze"):
    return request(
        client,
        "/packs",
        {"merchant_id": profile["merchant_id"], "case_id": case_id, "pack_type": pack_type, "sim_at": sim_at},
        "evidence",
    )


def fetch_artifact(client, path, *, role="officer"):
    api_path = path.removeprefix("/api")
    return client.get(api_path, headers={"X-Hisaab-Key": f"dev-{role}"})


def test_utr_and_amount_date_match_with_decoy_listed_not_selected(api, pack_root, quiet):
    client, connection, profile = api
    bill_id = f"B-{uuid4().hex[:8]}"
    target = credit_with_bill(
        client,
        profile,
        bill_id=bill_id,
        ts="2026-03-21T19:47:00+05:30",
        channel="UPI_POS",
        bill_items=[("Onions", 4200)],
    )
    connection.execute(text("UPDATE rails.credits SET utr = :utr WHERE txn_id = :txn"), {"utr": "608019038619", "txn": target["txn_id"]})
    target["utr"] = "608019038619"
    decoy = payment(client, profile, amount=4200, ts="2026-03-18T12:00:00+05:30", name="REGULAR CUSTOMER")
    event = lien_event(profile, disputed_utr=target["utr"])
    case_id = send_events(client, [event], sim_at=LIEN_AT)["opened_case_ids"][0]
    response = isolate(client, profile, case_id, disputed_utr=target["utr"])
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["found_by"] == ["utr", "amount_date"]
    assert body["matched"]["txn_id"] == target["txn_id"]
    assert body["same_amount_candidates"][0]["txn_id"] == decoy["txn_id"]
    assert body["seven_day_credit_count"] == 2


def test_amount_date_fallback_without_utr(api, pack_root, quiet):
    client, connection, profile = api
    target = payment(client, profile, amount=4200, ts="2026-03-21T10:00:00+05:30")
    event = lien_event(profile, disputed_utr="000000000000")
    case_id = send_events(client, [event], sim_at=LIEN_AT)["opened_case_ids"][0]
    body = isolate(client, profile, case_id, disputed_utr="000000000000").json()
    assert body["found_by"] == ["amount_date"]
    assert body["matched"]["txn_id"] == target["txn_id"]


def test_utr_only_when_amount_date_contradicts(api, pack_root, quiet):
    client, connection, profile = api
    target = payment(client, profile, amount=4200, ts="2026-03-21T10:00:00+05:30")
    connection.execute(text("UPDATE rails.credits SET utr = :utr WHERE txn_id = :txn"), {"utr": "608019038619", "txn": target["txn_id"]})
    event = lien_event(profile, disputed_utr="608019038619", disputed_date="2026-03-19")
    case_id = send_events(client, [event], sim_at=LIEN_AT)["opened_case_ids"][0]
    body = isolate(client, profile, case_id, disputed_utr="608019038619", disputed_date="2026-03-19").json()
    assert body["found_by"] == ["utr"]
    assert "amount_date" not in body["found_by"]


def test_ambiguous_amount_date_candidates_do_not_pick_a_decoy(api, pack_root, quiet):
    client, connection, profile = api
    payment(client, profile, amount=4200, ts="2026-03-21T10:00:00+05:30")
    payment(client, profile, amount=4200, ts="2026-03-21T11:00:00+05:30")
    event = lien_event(profile, disputed_utr="000000000000")
    case_id = send_events(client, [event], sim_at=LIEN_AT)["opened_case_ids"][0]
    body = isolate(client, profile, case_id, disputed_utr="000000000000").json()
    assert body["matched"] is None
    assert body["found_by"] == []
    assert len(body["same_amount_candidates"]) == 2


def test_bill_device_and_seven_day_boundaries(api, pack_root, quiet):
    client, connection, profile = api
    credit = credit_with_bill(
        client,
        profile,
        bill_id="B-1",
        ts="2026-03-21T10:00:00+05:30",
        channel="UPI_POS",
        bill_sim_at="2026-03-21T10:00:00+05:30",
        bill_items=[("Onions", 4200)],
    )
    connection.execute(
        text("UPDATE rails.credits SET utr = :utr, terminal_id = :terminal WHERE txn_id = :txn"),
        {"utr": "608019038619", "terminal": "POS01", "txn": credit["txn_id"]},
    )
    credit["utr"] = "608019038619"
    terminal(connection, profile, "POS01", "2026-03-01T00:00:00+05:30")
    payment(client, profile, amount=4200, ts="2026-03-17T09:30:00+05:30")
    payment(client, profile, amount=999, ts="2026-03-16T10:00:00+05:30")
    event = lien_event(profile, disputed_utr=credit["utr"])
    case_id = send_events(client, [event], sim_at=LIEN_AT)["opened_case_ids"][0]
    body = isolate(client, profile, case_id, disputed_utr=credit["utr"]).json()
    assert body["bill"]["total"] == 4200
    assert body["device"]["terminal_id"] == "POS01"
    assert body["seven_day_credit_count"] == 2


def test_post_cases_is_real_and_idempotent(api, pack_root, quiet):
    client, connection, profile = api
    event = lien_event(profile)
    send_events(client, [event], sim_at=LIEN_AT)
    case_id = f"CASE-FREEZE-{event['event_id']}"
    first = open_case(client, profile, event)
    assert first.status_code == 200, first.text
    assert first.json()["case_id"] == case_id
    clock(client, "2026-03-24T10:00:00+05:30")
    second = open_case(client, profile, event, sim_at="2026-03-24T10:00:00+05:30")
    second.raise_for_status()
    assert second.json()["ledger_entry"]["seq"] == first.json()["ledger_entry"]["seq"]
    assert connection.execute(
        text("SELECT count(*) FROM ledger.entries WHERE kind = 'case.opened' AND payload->>'case_id' = :case"),
        {"case": case_id},
    ).scalar_one() == 1


def test_post_cases_rejects_unknown_merchant(api, pack_root, quiet):
    client, connection, profile = api
    event = lien_event(profile)
    response = request(
        client,
        "/cases",
        {"merchant_id": "missing-merchant", "case_type": "freeze", "trigger_ref": event["event_id"], "sim_at": LIEN_AT},
        "evidence",
    )
    assert response.status_code == 404


def test_post_packs_writes_real_artifacts_and_records_ops(api, pack_root, quiet):
    client, connection, profile = api
    credit = credit_with_bill(
        client,
        profile,
        ts="2026-03-21T10:00:00+05:30",
        channel="UPI_POS",
        bill_sim_at="2026-03-21T10:00:00+05:30",
        bill_items=[("Onions", 4200)],
    )
    connection.execute(text("UPDATE rails.credits SET utr = :utr WHERE txn_id = :txn"), {"utr": "608019038619", "txn": credit["txn_id"]})
    terminal(connection, profile, credit["terminal_id"], "2026-03-01T00:00:00+05:30")
    event = lien_event(profile, disputed_utr="608019038619")
    case_id = send_events(client, [event], sim_at=LIEN_AT)["opened_case_ids"][0]
    built = build(client, profile, case_id)
    assert built.status_code == 200, built.text
    payload = built.json()
    assert payload["ledger_entry"]["kind"] == "pack.built"
    pdf_bytes = pack_root.joinpath(f"{payload['pack_id']}.pdf").read_bytes()
    assert payload["pdf_sha256"] == sha256_bytes(pdf_bytes)
    json_payload = json.loads(pack_root.joinpath(f"{payload['pack_id']}.json").read_text())
    assert json_payload["grading"] == "tier_1"
    assert json_payload["isolation"]["device"]["device_id"] == "DEV01"
    row = connection.execute(text("SELECT * FROM ops.packs WHERE pack_id = :pack"), {"pack": payload["pack_id"]}).mappings().one()
    assert row["data"]["pdf_url"] == f"/api/packs/{payload['pack_id']}.pdf"
    assert client.get(payload["json_path"].removeprefix("/api")).status_code == 403
    assert fetch_artifact(client, payload["json_path"], role="app").status_code == 403
    assert fetch_artifact(client, payload["json_path"], role="officer").status_code == 200
    assert fetch_artifact(client, payload["pdf_path"], role="officer").content == pdf_bytes
    assert pdf_bytes.startswith(b"%PDF-")


def test_pack_build_rejects_pre_case_and_future_times(api, pack_root, quiet):
    client, connection, profile = api
    credit = payment(client, profile, amount=4200, ts="2026-03-21T10:00:00+05:30")
    connection.execute(text("UPDATE rails.credits SET utr = :utr WHERE txn_id = :txn"), {"utr": "608019038619", "txn": credit["txn_id"]})
    event = lien_event(profile, disputed_utr="608019038619")
    case_id = send_events(client, [event], sim_at=LIEN_AT)["opened_case_ids"][0]
    assert build(client, profile, case_id, sim_at="2026-03-24T09:00:00+05:30").status_code == 422
    clock(client, "2026-03-24T11:00:00+05:30")
    assert build(client, profile, case_id, sim_at="2026-03-24T11:30:00+05:30").status_code == 422


def test_identical_pack_retry_reuses_entry_and_later_build_wins(api, pack_root, quiet):
    client, connection, profile = api
    credit = payment(client, profile, amount=4200, ts="2026-03-21T10:00:00+05:30")
    connection.execute(text("UPDATE rails.credits SET utr = :utr WHERE txn_id = :txn"), {"utr": "608019038619", "txn": credit["txn_id"]})
    event = lien_event(profile, disputed_utr="608019038619")
    case_id = send_events(client, [event], sim_at=LIEN_AT)["opened_case_ids"][0]
    first = build(client, profile, case_id).json()
    again = build(client, profile, case_id).json()
    assert again["pack_id"] == first["pack_id"]
    assert again["ledger_entry"]["seq"] == first["ledger_entry"]["seq"]
    pack_root.joinpath(f"{first['pack_id']}.pdf").unlink()
    assert build(client, profile, case_id).status_code == 500
    clock(client, "2026-03-24T10:05:00+05:30")
    later = build(client, profile, case_id, sim_at="2026-03-24T10:05:00+05:30").json()
    assert later["pack_id"] != first["pack_id"]
    detail = read(client, f"/app/officer/cases/{case_id}", role="officer").json()
    assert detail["pack_id"] == later["pack_id"]


def test_pack_grading_pre_case_answer_and_late_annotation(api, pack_root, quiet, monkeypatch):
    client, connection, profile = api
    credit = payment(client, profile, amount=4200, ts="2026-03-21T10:00:00+05:30")
    connection.execute(text("UPDATE rails.credits SET utr = :utr WHERE txn_id = :txn"), {"utr": "608019038619", "txn": credit["txn_id"]})
    with monkeypatch.context() as context:
        context.setattr(payment_helpers, "NOW", "2026-03-22T09:00:00+05:30")
        propose(client, credit)
        question_body, _ = ask(client, credit)
    request(
        client,
        "/ledger/claims",
        {
            "merchant_id": profile["merchant_id"],
            "txn_id": credit["txn_id"],
            "action": "answered",
            "sim_at": "2026-03-22T10:00:00+05:30",
            "claim": {
                "question_id": question_body["question"]["question_id"],
                "answer": "family",
                "raw_text": "From family.",
                "language": "en",
            },
        },
        "conversation",
    ).raise_for_status()
    event = lien_event(profile, disputed_utr="608019038619")
    case_id = send_events(client, [event], sim_at=LIEN_AT)["opened_case_ids"][0]
    answered = build(client, profile, case_id).json()
    assert json.loads(pack_root.joinpath(f"{answered['pack_id']}.json").read_text())["grading"] == "tier_3"
    clock(client, "2026-03-24T10:10:00+05:30")
    request(
        client,
        "/ledger/claims",
        {
            "merchant_id": profile["merchant_id"],
            "txn_id": credit["txn_id"],
            "action": "annotated",
            "sim_at": "2026-03-24T10:00:00+05:30",
            "claim": {"label": "personal_transfer", "raw_text": "Actually personal.", "language": "en"},
        },
        "conversation",
    ).raise_for_status()
    clock(client, "2026-03-24T10:10:00+05:30")
    annotated = build(client, profile, case_id, sim_at="2026-03-24T10:10:00+05:30").json()
    assert json.loads(pack_root.joinpath(f"{annotated['pack_id']}.json").read_text())["grading"] == "tier_4"


def test_end_to_end_lien_pack_officer_send(api, pack_root, quiet):
    client, connection, profile = api
    credit = credit_with_bill(
        client,
        profile,
        ts="2026-03-21T10:00:00+05:30",
        channel="UPI_POS",
        bill_sim_at="2026-03-21T10:00:00+05:30",
        bill_items=[("Onions", 4200)],
    )
    connection.execute(text("UPDATE rails.credits SET utr = :utr WHERE txn_id = :txn"), {"utr": "608019038619", "txn": credit["txn_id"]})
    case_id = send_events(client, [lien_event(profile, disputed_utr="608019038619")], sim_at=LIEN_AT)["opened_case_ids"][0]
    clock(client, SENT)
    built = build(client, profile, case_id).json()
    pack_id = built["pack_id"]
    pdf_bytes = pack_root.joinpath(f"{pack_id}.pdf").read_bytes()
    assert built["pdf_sha256"] == sha256_bytes(pdf_bytes)
    assert fetch_artifact(client, built["pdf_path"], role="officer").content == pdf_bytes
    assert approve(client, pack_id).status_code == 200
    assert send(client, pack_id).status_code == 200
    assert read(client, "/app/officer/outbox", role="officer").json()["items"][0]["pack_id"] == pack_id
    assert read(client, "/app/cases", profile["merchant_id"]).json()["items"][0]["status"] == "sent"
    assert read(client, f"/app/officer/cases/{case_id}", role="officer").json()["pack_id"] == pack_id


def test_rejected_pack_is_not_sent(api, pack_root, quiet):
    client, connection, profile = api
    credit = payment(client, profile, amount=4200, ts="2026-03-21T10:00:00+05:30")
    connection.execute(text("UPDATE rails.credits SET utr = :utr WHERE txn_id = :txn"), {"utr": "608019038619", "txn": credit["txn_id"]})
    case_id = send_events(client, [lien_event(profile, disputed_utr="608019038619")], sim_at=LIEN_AT)["opened_case_ids"][0]
    clock(client, SENT)
    pack_id = build(client, profile, case_id).json()["pack_id"]
    reject(client, pack_id)
    assert send(client, pack_id).status_code == 409


def test_artifact_download_hidden_before_pack_built(api, pack_root, quiet):
    client, connection, profile = api
    credit = payment(client, profile, amount=4200, ts="2026-03-21T10:00:00+05:30")
    connection.execute(text("UPDATE rails.credits SET utr = :utr WHERE txn_id = :txn"), {"utr": "608019038619", "txn": credit["txn_id"]})
    case_id = send_events(client, [lien_event(profile, disputed_utr="608019038619")], sim_at=LIEN_AT)["opened_case_ids"][0]
    built = build(client, profile, case_id).json()
    assert fetch_artifact(client, built["pdf_path"], role="officer").status_code == 200
    clock(client, "2026-03-24T09:00:00+05:30")
    assert fetch_artifact(client, built["pdf_path"], role="officer").status_code == 404


def test_notice_pack_build_is_refused(api, pack_root, quiet):
    client, connection, profile = api
    event_id = f"E-{uuid4().hex}"
    connection.execute(
        text("""INSERT INTO rails.events (event_id, merchant_id, ts, type, data)
                VALUES (:event, :merchant, :ts, 'notice_served', CAST(:data AS jsonb))"""),
        {
            "event": event_id,
            "merchant": profile["merchant_id"],
            "ts": datetime.fromisoformat(LIEN_AT),
            "data": json.dumps(
                {
                    "event_id": event_id,
                    "merchant_id": profile["merchant_id"],
                    "ts": LIEN_AT,
                    "type": "notice_served",
                    "document": "GSTR-3B",
                    "photo": None,
                    "note": "Synthetic",
                }
            ),
        },
    )
    opened = open_case(client, profile, {"event_id": event_id}, case_type="notice", sim_at=LIEN_AT)
    case_id = opened.json()["case_id"]
    response = build(client, profile, case_id, pack_type="notice")
    assert response.status_code == 422
