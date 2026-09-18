"""6.10: an officer's one decision per pack, and an outbox that reads that decision from the ledger."""

from datetime import datetime
from uuid import uuid4

import pytest
from sqlalchemy import text

from app.cases import approvals
from app.ledger.chain import append
from app.schemas.ledger import EntryKind
from app.schemas.roles import Role
from app.cases.packs import record_pack
from test_freeze_postgres import lien, send as send_events
from test_payments_postgres import api, read, request  # noqa: F401  (api is a fixture)


pytestmark = pytest.mark.postgres

BUILT = "2026-03-24T10:05:00+05:30"
DECIDED = "2026-03-24T10:20:00+05:30"
SENT = "2026-03-24T10:25:00+05:30"
TIERS = {"1": {"amount": 4200, "count": 1}}


@pytest.fixture
def resumes(monkeypatch):
    calls = []
    monkeypatch.setattr(approvals, "resume", lambda url, body: calls.append((url, body)))
    return calls


@pytest.fixture
def built(api, resumes):
    """A real case opened by a real lien, with a pack recorded against it (the PDF is 6.8's)."""
    client, connection, profile = api
    case_id = send_events(client, [lien(profile)])["opened_case_ids"][0]
    request(client, "/sim/clock", {"sim_at": SENT}, "admin").raise_for_status()

    def make(resume_url=None):
        pack_id = f"PACK-{uuid4().hex}"
        record_pack(connection, merchant_id=profile["merchant_id"], case_id=case_id, pack_id=pack_id, pack_type="freeze",
                    pdf_sha256="0" * 64, tier_totals=TIERS, built_at=datetime.fromisoformat(BUILT), resume_url=resume_url)
        return pack_id
    return make


def approve(client, pack_id, *, role="officer", sim_at=DECIDED, note="Isolation checks out.", officer="OFF-1"):
    return request(client, f"/packs/{pack_id}/approve", {"officer_ref": officer, "note": note, "sim_at": sim_at}, role)


def reject(client, pack_id, *, role="officer", sim_at=DECIDED, reason="Decoy not ruled out.", officer="OFF-1"):
    return request(client, f"/packs/{pack_id}/reject", {"officer_ref": officer, "reason": reason, "sim_at": sim_at}, role)


def send(client, pack_id, *, role="officer", sim_at=SENT, destination="bank-nodal-and-ncrp"):
    return request(client, f"/outbox/{pack_id}/send", {"destination": destination, "sim_at": sim_at}, role)


def kinds(client, profile, pack_id):
    entries = read(client, f"/ledger/{profile['merchant_id']}/entries", role="officer", limit=200).json()["entries"]
    return [entry["kind"] for entry in entries if entry["payload"].get("pack_id") == pack_id]


def outbox(connection, pack_id):
    return connection.execute(text("SELECT * FROM ops.outbox WHERE pack_id = :pack"), {"pack": pack_id}).mappings().all()


def test_an_unapproved_pack_is_refused_and_nothing_leaves(api, built):
    client, connection, profile = api
    pack_id = built()
    response = send(client, pack_id)
    assert response.status_code == 409
    assert "no officer approval" in response.json()["detail"]
    assert outbox(connection, pack_id) == []
    assert kinds(client, profile, pack_id) == ["pack.built"]


def test_the_gate_reads_the_ledger_not_the_status_column(api, built):
    client, connection, profile = api
    pack_id = built()
    # ops is working state the application role may UPDATE. If the gate trusted it, anything
    # holding that connection could approve a pack by editing one row.
    connection.execute(text("UPDATE ops.approvals SET status = 'approved', officer_ref = 'nobody' WHERE pack_id = :pack"), {"pack": pack_id})
    assert send(client, pack_id).status_code == 409
    assert outbox(connection, pack_id) == []


def test_an_approved_pack_is_sent_once_simulated_and_the_chain_holds(api, built):
    client, connection, profile = api
    pack_id = built()
    approved = approve(client, pack_id)
    assert approved.status_code == 200, approved.text
    body = approved.json()
    assert body["status"] == "approved" and body["workflow_resumed"] is False
    assert body["ledger_entry"]["kind"] == "pack.approved"
    assert body["ledger_entry"]["actor_role"] == "officer" and body["ledger_entry"]["actor_ref"] == "OFF-1"
    assert body["ledger_entry"]["payload"] == {"pack_id": pack_id, "note": "Isolation checks out."}

    sent = send(client, pack_id)
    assert sent.status_code == 200, sent.text
    delivery = sent.json()
    assert delivery["sent"] is True and delivery["simulated"] is True
    assert delivery["delivery_ref"] == f"SIM-{pack_id}"
    assert delivery["ledger_entry"]["payload"] == {"pack_id": pack_id, "destination": "bank-nodal-and-ncrp",
                                                   "delivery_ref": f"SIM-{pack_id}"}
    [row] = outbox(connection, pack_id)
    assert row["simulated"] is True
    status = connection.execute(text("SELECT status FROM ops.approvals WHERE pack_id = :pack"), {"pack": pack_id}).scalar_one()
    assert status == "sent"
    assert kinds(client, profile, pack_id) == ["pack.built", "pack.approved", "pack.sent"]
    assert read(client, "/ledger/verify", profile["merchant_id"], role="officer").json()["ok"]


def test_a_rejected_pack_cannot_be_sent(api, built):
    client, connection, profile = api
    pack_id = built()
    assert reject(client, pack_id).json()["status"] == "rejected"
    assert send(client, pack_id).status_code == 409
    assert outbox(connection, pack_id) == []


def test_a_rejection_anywhere_in_the_ledger_blocks_the_send_even_beside_an_approval(api, built):
    client, connection, profile = api
    pack_id = built()
    approve(client, pack_id)
    # Unreachable through the routes while decisions are final. The outbox must not depend on that:
    # if the ledger ever holds both, it refuses rather than picking the approval.
    append(connection, merchant_id=profile["merchant_id"], kind=EntryKind.PACK_REJECTED, actor_role=Role.OFFICER,
           actor_ref="OFF-2", sim_at=datetime.fromisoformat(DECIDED), payload={"pack_id": pack_id, "reason": "Late objection."})
    assert send(client, pack_id).status_code == 409
    assert outbox(connection, pack_id) == []


def test_another_packs_approval_does_not_open_the_gate(api, built):
    client, connection, profile = api
    approved, waiting = built(), built()
    approve(client, approved)
    assert send(client, waiting).status_code == 409
    assert outbox(connection, waiting) == []


@pytest.mark.parametrize("first, second", [(approve, reject), (reject, approve)], ids=["approve then reject", "reject then approve"])
def test_a_decision_is_final(api, built, first, second):
    client, connection, profile = api
    pack_id = built()
    assert first(client, pack_id).status_code == 200
    changed = second(client, pack_id)
    assert changed.status_code == 409
    assert "final" in changed.json()["detail"]
    assert len([kind for kind in kinds(client, profile, pack_id) if kind in approvals.DECISION_KINDS]) == 1


def test_an_identical_retry_returns_the_original_decision_and_a_different_one_is_refused(api, built):
    client, connection, profile = api
    pack_id = built()
    first = approve(client, pack_id).json()["ledger_entry"]
    assert approve(client, pack_id).json()["ledger_entry"]["seq"] == first["seq"]
    assert approve(client, pack_id, note="Changed my mind about the wording.").status_code == 409
    assert approve(client, pack_id, officer="OFF-2").status_code == 409
    assert kinds(client, profile, pack_id).count("pack.approved") == 1


def test_a_send_retry_is_the_same_delivery_and_a_new_destination_is_refused(api, built):
    client, connection, profile = api
    pack_id = built()
    approve(client, pack_id)
    first = send(client, pack_id).json()
    again = send(client, pack_id)
    assert again.status_code == 200 and again.json()["ledger_entry"]["seq"] == first["ledger_entry"]["seq"]
    assert send(client, pack_id, destination="somewhere-else").status_code == 409
    assert len(outbox(connection, pack_id)) == 1
    assert kinds(client, profile, pack_id).count("pack.sent") == 1


def test_business_time_runs_forwards_through_build_decision_and_send(api, built):
    client, connection, profile = api
    pack_id = built()
    assert approve(client, pack_id, sim_at="2026-03-24T10:00:00+05:30").status_code == 422   # before the pack was built
    assert approve(client, pack_id, sim_at="2026-03-24T11:00:00+05:30").status_code == 422   # after the sim clock
    assert approve(client, pack_id).status_code == 200
    assert send(client, pack_id, sim_at="2026-03-24T10:10:00+05:30").status_code == 422      # before it was approved
    assert outbox(connection, pack_id) == []


def test_only_the_officer_decides_or_sends(api, built):
    client, connection, profile = api
    pack_id = built()
    for role in ("evidence", "rails", "provenance", "conversation", "app"):
        assert approve(client, pack_id, role=role).status_code == 403, role
        assert reject(client, pack_id, role=role).status_code == 403, role
    approve(client, pack_id)
    for role in ("evidence", "rails", "provenance", "conversation", "app"):
        assert send(client, pack_id, role=role).status_code == 403, role
    assert outbox(connection, pack_id) == []


def test_an_unknown_pack_is_not_found(api, built):
    client, connection, profile = api
    assert approve(client, "PACK-missing").status_code == 404
    assert send(client, "PACK-missing").status_code == 404


def test_the_waiting_workflow_is_resumed_only_at_our_own_n8n(api, built, resumes):
    client, connection, profile = api
    ours = built(resume_url="http://n8n:5678/webhook-waiting/4711")
    body = approve(client, ours).json()
    assert body["workflow_resumed"] is True
    assert resumes == [("http://n8n:5678/webhook-waiting/4711", {"pack_id": ours, "decision": "approved",
                                                                 "entry_seq": body["ledger_entry"]["seq"]})]
    # The resume call carries the webhook secret, so a stored URL elsewhere must not receive it.
    elsewhere = built(resume_url="https://attacker.example/collect")
    assert approve(client, elsewhere).json()["workflow_resumed"] is False
    assert len(resumes) == 1
