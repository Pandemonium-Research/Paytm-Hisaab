"""6.11: case and officer read models respect the sim clock and ledger evidence."""

import json
from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.cases import reads
from app.cases.packs import record_pack
from app.rails import freeze
from app.ledger.verify import verify
from test_approvals_postgres import BUILT, DECIDED, SENT, TIERS, approve, reject, send
from test_freeze_postgres import lien, send as send_events
from test_payments_postgres import api, read, request  # noqa: F401


pytestmark = pytest.mark.postgres

LIEN_AT = "2026-03-24T09:30:00+05:30"


def clock(client, sim_at):
    request(client, "/sim/clock", {"sim_at": sim_at}, "admin").raise_for_status()


def officer(client, path, **params):
    return read(client, path, role="officer", **params)


def merchant_cases(client, merchant_id):
    return read(client, "/app/cases", merchant_id).json()


@pytest.fixture
def freeze_case(api, monkeypatch):
    client, connection, profile = api
    monkeypatch.setattr(freeze, "notify", lambda body: True)
    case_id = send_events(client, [lien(profile)], sim_at=SENT)["opened_case_ids"][0]
    clock(client, SENT)

    def make_pack(*, tier_totals=TIERS, built_at=BUILT, data=None):
        pack_id = f"PACK-{uuid4().hex}"
        record_pack(
            connection,
            merchant_id=profile["merchant_id"],
            case_id=case_id,
            pack_id=pack_id,
            pack_type="freeze",
            pdf_sha256="0" * 64,
            tier_totals=tier_totals,
            built_at=datetime.fromisoformat(built_at),
            data=data,
        )
        return pack_id

    return client, connection, profile, case_id, make_pack


def test_unknown_merchant_and_empty_cases(api):
    client, connection, profile = api
    assert read(client, "/app/cases", "MID-NO-SUCH").status_code == 404
    assert merchant_cases(client, profile["merchant_id"]) == {"items": []}


def test_role_denial_and_two_merchants_stay_separate(api, freeze_case):
    client, connection, profile, case_id, _ = freeze_case
    assert read(client, "/app/officer/queue", role="app").status_code == 403
    other = {**profile, "merchant_id": f"test-{uuid4().hex}"}
    connection.execute(
        text("INSERT INTO rails.merchants (merchant_id, profile) VALUES (:merchant, CAST(:profile AS jsonb))"),
        {"merchant": other["merchant_id"], "profile": json.dumps({**other, "business_name": "Other Shop"})},
    )
    other_case = send_events(client, [lien(other)], sim_at=SENT)["opened_case_ids"][0]
    clock(client, SENT)
    queue = officer(client, "/app/officer/queue").json()["items"]
    ids = {row["case_id"] for row in queue}
    assert case_id in ids and other_case in ids
    assert len({row["merchant_id"] for row in queue if row["case_id"] in {case_id, other_case}}) == 2
    assert [row["case_id"] for row in merchant_cases(client, profile["merchant_id"])["items"]] == [case_id]
    assert [row["case_id"] for row in merchant_cases(client, other["merchant_id"])["items"]] == [other_case]
    assert officer(client, f"/app/officer/cases/{other_case}").json()["case"]["business_name"] == "Other Shop"


def test_lifecycle_ids_and_statuses_match_reads(freeze_case):
    client, connection, profile, case_id, make_pack = freeze_case
    pack_id = make_pack()
    approve(client, pack_id)
    send(client, pack_id)

    merchant = merchant_cases(client, profile["merchant_id"])["items"][0]
    assert merchant["case_id"] == case_id
    assert merchant["status"] == "sent"
    assert merchant["title"] == "Payments on hold"
    assert merchant["disputed_amount_text"] == "₹4,200"

    assert officer(client, "/app/officer/queue").json()["items"] == []

    detail = officer(client, f"/app/officer/cases/{case_id}").json()
    assert detail["pack_id"] == pack_id
    assert detail["status"] == "sent"
    assert detail["chain_ok"] is True
    assert detail["pdf_url"] is None
    assert detail["timeline"] == [
        "24 Mar 2026, 09:30 IST · Case opened",
        "24 Mar 2026, 10:05 IST · Pack built",
        "24 Mar 2026, 10:20 IST · Approved: Isolation checks out.",
        "24 Mar 2026, 10:25 IST · Pack sent",
    ]

    [row] = officer(client, "/app/officer/outbox").json()["items"]
    assert row["pack_id"] == pack_id and row["case_id"] == case_id
    assert row["delivery_ref"] == f"SIM-{pack_id}"
    assert row["outcome"] is None
    assert row["usable_balance"] == {"amount": 0, "amount_text": "₹0"}
    assert datetime.fromisoformat(row["sent_at"]) == datetime.fromisoformat(SENT)
    assert row["pack_to_approval_seconds"] == 15 * 60
    assert row["freeze_to_pack_seconds"] == int(
        (datetime.fromisoformat(BUILT) - datetime.fromisoformat(LIEN_AT)).total_seconds()
    )


def test_rejection_stays_rejected_and_ops_status_does_not_change_reads(freeze_case):
    client, connection, profile, case_id, make_pack = freeze_case
    pack_id = make_pack()
    reject(client, pack_id)
    connection.execute(text("UPDATE ops.approvals SET status = 'approved' WHERE pack_id = :pack"), {"pack": pack_id})

    assert merchant_cases(client, profile["merchant_id"])["items"][0]["status"] == "rejected"
    detail = officer(client, f"/app/officer/cases/{case_id}").json()
    assert detail["status"] == "rejected"
    assert any("Rejected: Decoy not ruled out." in line for line in detail["timeline"])
    assert officer(client, "/app/officer/outbox").json()["items"] == []


def test_latest_pack_wins_but_an_earlier_send_stays_in_outbox(freeze_case):
    client, connection, profile, case_id, make_pack = freeze_case
    first = make_pack()
    approve(client, first)
    send(client, first)
    second = make_pack()
    rows = officer(client, "/app/officer/outbox").json()["items"]
    assert {row["pack_id"] for row in rows} == {first}
    detail = officer(client, f"/app/officer/cases/{case_id}").json()
    assert detail["pack_id"] == second
    assert detail["status"] == "awaiting_approval"
    assert officer(client, "/app/officer/queue").json()["items"][0]["case_id"] == case_id


def test_weak_share_uses_tier_amounts(freeze_case):
    client, connection, profile, case_id, make_pack = freeze_case
    make_pack(
        tier_totals={"1": {"amount": 1000, "count": 1}, "3": {"amount": 3000, "count": 2}, "4": {"amount": 1000, "count": 1}},
    )
    share = officer(client, f"/app/officer/cases/{case_id}").json()["case"]["weak_evidence_share"]
    assert share == pytest.approx(0.8)
    assert reads.weak_evidence_share(None) == 0.0
    assert reads.weak_evidence_share({"1": {"amount": 0, "count": 0}}) == 0.0


def test_rewind_hides_future_stages(freeze_case):
    client, connection, profile, case_id, make_pack = freeze_case
    pack_id = make_pack(data={"pdf_url": "/api/packs/test-pack.pdf"})
    approve(client, pack_id)
    send(client, pack_id)

    clock(client, DECIDED)
    detail = officer(client, f"/app/officer/cases/{case_id}").json()
    assert detail["status"] == "approved"
    assert not any("Pack sent" in line for line in detail["timeline"])
    assert officer(client, "/app/officer/outbox").json()["items"] == []
    assert officer(client, "/app/officer/queue").json()["items"] == []

    clock(client, BUILT)
    detail = officer(client, f"/app/officer/cases/{case_id}").json()
    assert detail["status"] == "awaiting_approval"
    assert detail["tier_totals"][0]["amount"] == 4200
    assert not any("Approved" in line or "Pack sent" in line for line in detail["timeline"])
    assert detail["pdf_url"] == "/api/packs/test-pack.pdf"
    assert officer(client, "/app/officer/queue").json()["items"]

    clock(client, LIEN_AT)
    assert merchant_cases(client, profile["merchant_id"])["items"][0]["status"] == "open"
    detail = officer(client, f"/app/officer/cases/{case_id}").json()
    assert detail["pack_id"] is None and detail["pdf_url"] is None
    assert detail["tier_totals"] == [] and detail["case"]["weak_evidence_share"] == 0
    assert detail["timeline"] == ["24 Mar 2026, 09:30 IST · Case opened"]

    clock(client, "2026-03-24T09:00:00+05:30")
    assert merchant_cases(client, profile["merchant_id"])["items"] == []
    assert officer(client, f"/app/officer/cases/{case_id}").status_code == 404


def test_detail_chain_ok_calls_verify(freeze_case, monkeypatch):
    client, connection, profile, case_id, make_pack = freeze_case
    make_pack()
    calls = []

    def counting_verify(connection, merchant_id):
        calls.append(merchant_id)
        return verify(connection, merchant_id)

    monkeypatch.setattr(reads, "verify", counting_verify)
    assert officer(client, f"/app/officer/cases/{case_id}").json()["chain_ok"] is True
    assert calls == [profile["merchant_id"]]

    def broken_verify(connection, merchant_id):
        calls.append(merchant_id)
        from app.schemas.api.ledger_ops import LedgerVerifyResponse

        return LedgerVerifyResponse(merchant_id=merchant_id, ok=False, broken_at=1)

    monkeypatch.setattr(reads, "verify", broken_verify)
    assert officer(client, f"/app/officer/cases/{case_id}").json()["chain_ok"] is False
    assert calls.count(profile["merchant_id"]) == 2


def test_unknown_officer_case_is_not_found(freeze_case):
    client, connection, profile, case_id, _ = freeze_case
    assert officer(client, "/app/officer/cases/CASE-missing").status_code == 404


def test_escalations_are_scoped_to_the_case_and_business_time(freeze_case):
    client, connection, profile, case_id, make_pack = freeze_case
    make_pack()
    for identifier, named_case, sim_at, reason in (
        ("visible", case_id, BUILT, "Needs review"),
        ("future", case_id, "2026-03-25T10:00:00+05:30", "Future finding"),
        ("other", "CASE-OTHER", BUILT, "Other case finding"),
    ):
        connection.execute(
            text("""INSERT INTO ops.escalations (escalation_id, merchant_id, data)
                    VALUES (:id, :merchant, CAST(:data AS jsonb))"""),
            {"id": f"{identifier}-{uuid4().hex}", "merchant": profile["merchant_id"],
             "data": json.dumps({"case_id": named_case, "sim_at": sim_at, "reasons": [reason]})},
        )
    detail = officer(client, f"/app/officer/cases/{case_id}").json()
    assert detail["status"] == "escalated"
    assert detail["case"]["escalation_reasons"] == ["Needs review"]
    assert "24 Mar 2026, 10:05 IST · Escalated: Needs review" in detail["timeline"]
    approve(client, detail["pack_id"])
    assert officer(client, f"/app/officer/cases/{case_id}").json()["status"] == "approved"


def test_a_delivery_cannot_borrow_another_packs_send_or_build(freeze_case):
    client, connection, profile, case_id, make_pack = freeze_case
    first, second = make_pack(), make_pack()
    approve(client, first).raise_for_status()
    approve(client, second).raise_for_status()
    first_send = send(client, first).json()["ledger_entry"]["seq"]
    send(client, second).raise_for_status()
    connection.execute(
        text("UPDATE ops.outbox SET data = jsonb_set(data, '{entry_seq}', CAST(:seq AS jsonb)) WHERE pack_id = :pack"),
        {"seq": json.dumps(first_send), "pack": second},
    )
    assert [row["pack_id"] for row in officer(client, "/app/officer/outbox").json()["items"]] == [first]
    connection.execute(
        text("""UPDATE ops.packs SET data = jsonb_set(data, '{entry_seq}',
                (SELECT data->'entry_seq' FROM ops.packs WHERE pack_id = :second)) WHERE pack_id = :first"""),
        {"first": first, "second": second},
    )
    assert officer(client, "/app/officer/outbox").json()["items"] == []


def test_future_or_unknown_cases_do_not_verify_a_chain(freeze_case, monkeypatch):
    client, connection, profile, case_id, _ = freeze_case
    monkeypatch.setattr(reads, "verify", lambda *args: pytest.fail("An invisible case must not run verification"))
    assert officer(client, "/app/officer/cases/CASE-missing").status_code == 404
    clock(client, "2026-03-24T09:00:00+05:30")
    assert officer(client, f"/app/officer/cases/{case_id}").status_code == 404
