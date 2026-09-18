"""6.8: explicit freeze/notice case creation from a visible rails trigger."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import text

from ..ledger.chain import lock_head
from ..ledger.mutations import validate_time, wire_entry
from ..ledger.projection import merchant
from ..rails import freeze
from ..schemas.api.cases import CreateCaseRequest, CreateCaseResponse
from ..schemas.ledger import EntryKind, LedgerEntry


def _case_id(case_type: str, event_id: str) -> str:
    prefix = "CASE-FREEZE" if case_type == "freeze" else "CASE-NOTICE"
    return f"{prefix}-{event_id}"


def _trigger_type(case_type: str) -> str:
    return "lien_marked" if case_type == "freeze" else "notice_served"


def _case_opened_entry(connection, merchant_id: str, case_id: str):
    row = connection.execute(
        text("""SELECT * FROM ledger.entries
                WHERE merchant_id = :merchant AND kind = :kind AND payload->>'case_id' = :case
                ORDER BY chain_index LIMIT 1"""),
        {"merchant": merchant_id, "kind": EntryKind.CASE_OPENED.value, "case": case_id},
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(500, f"Case {case_id} exists without a ledger entry.")
    return wire_entry(LedgerEntry.model_validate(dict(row)))


def _lien_data(event_row) -> dict:
    data = event_row["data"] if isinstance(event_row["data"], dict) else {}
    return {
        "lien": {
            "event_id": event_row["event_id"],
            "ts": event_row["ts"].isoformat(),
            "authority": data.get("authority"),
            "case_ref": data.get("case_ref"),
            "ncrp_ack": data.get("ncrp_ack"),
            "disputed_amount": data.get("disputed_amount"),
            "disputed_utr": data.get("disputed_utr"),
            "disputed_date": data.get("disputed_date"),
        },
        "decline_burst": None,
    }


def _notice_data(event_row) -> dict:
    data = event_row["data"] if isinstance(event_row["data"], dict) else {}
    return {
        "notice": {
            "event_id": event_row["event_id"],
            "ts": event_row["ts"].isoformat(),
            "document": data.get("document"),
            "photo": data.get("photo"),
            "note": data.get("note"),
        }
    }


def create_case(connection, body: CreateCaseRequest, role) -> CreateCaseResponse:
    validate_time(connection, body.sim_at)
    merchant(connection, body.merchant_id)
    lock_head(connection, body.merchant_id)
    expected_type = _trigger_type(body.case_type)
    event = connection.execute(
        text("""SELECT * FROM rails.events WHERE event_id = :event AND merchant_id = :merchant
                AND ts <= :sim_at"""),
        {"event": body.trigger_ref, "merchant": body.merchant_id, "sim_at": body.sim_at},
    ).mappings().one_or_none()
    if event is None or event["type"] != expected_type:
        raise HTTPException(422, "The trigger does not match this merchant, case type, or business time.")
    if event["ts"] > body.sim_at:
        raise HTTPException(422, "Case creation cannot use a visibility cutoff before the trigger.")

    case_id = _case_id(body.case_type, body.trigger_ref)
    existing = connection.execute(
        text("SELECT case_id FROM ops.cases WHERE case_id = :case"), {"case": case_id},
    ).scalar_one_or_none()
    if existing is not None:
        return CreateCaseResponse(case_id=case_id, ledger_entry=_case_opened_entry(connection, body.merchant_id, case_id))

    if body.case_type == "freeze":
        burst = freeze.decline_burst(connection, body.merchant_id, event["ts"])
        payload = _lien_data(event)
        payload["decline_burst"] = burst
    else:
        payload = _notice_data(event)

    opened_id, entry = freeze.open_case(
        connection,
        merchant_id=body.merchant_id,
        case_type=body.case_type,
        trigger_ref=body.trigger_ref,
        sim_at=event["ts"],
        actor_role=role,
        actor_ref="cases",
        case_id=case_id,
        data=payload,
    )
    if entry is None:
        return CreateCaseResponse(case_id=opened_id, ledger_entry=_case_opened_entry(connection, body.merchant_id, opened_id))
    return CreateCaseResponse(case_id=opened_id, ledger_entry=wire_entry(entry))
