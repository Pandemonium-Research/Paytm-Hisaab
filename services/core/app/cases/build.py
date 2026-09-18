"""6.8: build freeze evidence packs with real isolation facts and ledger recording."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import text

from ..ledger.chain import lock_head
from ..ledger.mutations import validate_time, wire_entry
from ..ledger.projection import merchant
from ..schemas.api.cases import BuildPackRequest, BuildPackResponse
from ..schemas.api.skills import BillEvidence, IsolateRequest
from ..schemas.ledger import EntryKind, LedgerEntry
from ..skills.isolate import isolate
from .artifacts import (
    pack_paths,
    pack_pdf_sections,
    public_pdf_url,
    sha256_bytes,
    write_json,
    write_pdf,
)
from .packs import record_pack

IST = ZoneInfo("Asia/Kolkata")
TIER_KEYS = ("1", "2", "3", "4")


def _format_ist(value: datetime) -> str:
    return value.astimezone(IST).strftime("%d %b %Y, %H:%M IST")


def _empty_tiers() -> dict:
    return {key: {"amount": 0, "count": 0} for key in TIER_KEYS}


def _ledger_refs(connection, merchant_id: str, seqs: list[int]) -> list[dict]:
    if not seqs:
        return []
    rows = connection.execute(
        text("""SELECT seq, kind, hash FROM ledger.entries
                WHERE merchant_id = :merchant AND seq = ANY(:seqs) ORDER BY chain_index"""),
        {"merchant": merchant_id, "seqs": seqs},
    ).mappings().all()
    return [{"seq": int(row["seq"]), "kind": row["kind"], "hash": row["hash"].hex()} for row in rows]


def _case_opened_seq(connection, merchant_id: str, case_id: str) -> int | None:
    return connection.execute(
        text("""SELECT seq FROM ledger.entries
                WHERE merchant_id = :merchant AND kind = :kind AND payload->>'case_id' = :case
                ORDER BY chain_index LIMIT 1"""),
        {"merchant": merchant_id, "kind": EntryKind.CASE_OPENED.value, "case": case_id},
    ).scalar_one_or_none()


def _bill_linked_seq(connection, merchant_id: str, txn_id: str, bill_id: str, as_of: datetime, opened_at: datetime) -> int | None:
    return connection.execute(
        text("""SELECT seq FROM ledger.entries
                WHERE merchant_id = :merchant AND txn_id = :txn AND kind = 'bill.linked'
                  AND payload->>'bill_id' = :bill AND sim_at < :opened AND sim_at <= :as_of
                ORDER BY chain_index DESC LIMIT 1"""),
        {"merchant": merchant_id, "txn": txn_id, "bill": bill_id, "opened": opened_at, "as_of": as_of},
    ).scalar_one_or_none()


def _tier_for_payment(
    connection,
    merchant_id: str,
    case_id: str,
    txn_id: str,
    opened_at: datetime,
    as_of: datetime,
    validated_bill: BillEvidence | None,
) -> tuple[str | None, list[int]]:
    projection = connection.execute(
        text("SELECT conflict, entry_refs FROM ledger.current_view(:merchant, :as_of) WHERE txn_id = :txn"),
        {"merchant": merchant_id, "as_of": as_of, "txn": txn_id},
    ).mappings().one_or_none()
    conflict = bool(projection and projection["conflict"])

    latest_claim = connection.execute(
        text("""SELECT seq, kind, sim_at FROM ledger.entries
                WHERE merchant_id = :merchant AND txn_id = :txn
                  AND kind IN ('claim.annotated', 'claim.answered')
                  AND sim_at <= :as_of
                ORDER BY chain_index DESC LIMIT 1"""),
        {"merchant": merchant_id, "txn": txn_id, "as_of": as_of},
    ).mappings().one_or_none()

    refs: list[int] = list(projection["entry_refs"] or []) if projection else []
    opened_seq = _case_opened_seq(connection, merchant_id, case_id)
    if opened_seq is not None:
        refs.append(int(opened_seq))

    # A machine proposal never replaces the merchant's independently recorded answer.
    latest = latest_claim or connection.execute(
        text("""SELECT seq, kind, sim_at FROM ledger.entries
                WHERE merchant_id = :merchant AND txn_id = :txn AND kind = 'label.proposed'
                  AND sim_at <= :as_of ORDER BY chain_index DESC LIMIT 1"""),
        {"merchant": merchant_id, "txn": txn_id, "as_of": as_of},
    ).mappings().one_or_none()

    if validated_bill:
        bill_seq = _bill_linked_seq(connection, merchant_id, txn_id, validated_bill.bill_id, as_of, opened_at)
        if bill_seq is not None:
            refs.append(int(bill_seq))
            if not conflict:
                return "1", refs

    if latest is not None:
        refs.append(int(latest["seq"]))
        if latest["sim_at"] >= opened_at or latest["kind"] == EntryKind.CLAIM_ANNOTATED.value:
            return "4", refs
        if latest["kind"] == EntryKind.CLAIM_ANSWERED.value:
            answered = connection.execute(
                text("""SELECT 1 FROM ledger.entries e
                        JOIN ops.questions q ON q.question_id = e.payload->>'question_id'
                        WHERE e.seq = :seq AND q.merchant_id = :merchant AND q.txn_id = :txn"""),
                {"seq": latest["seq"], "merchant": merchant_id, "txn": txn_id},
            ).scalar_one_or_none()
            if answered:
                return "3", refs
            return "4", refs
        if latest["kind"] == EntryKind.LABEL_PROPOSED.value:
            return "2", refs

    return None, refs


def _existing_build(connection, body: BuildPackRequest):
    return connection.execute(
        text("""SELECT p.*, e.seq AS entry_seq FROM ops.packs p
                JOIN ledger.entries e ON e.seq = (p.data->>'entry_seq')::bigint
                WHERE p.merchant_id = :merchant AND p.case_id = :case AND p.pack_type = :type
                  AND p.built_at = :built AND e.kind = 'pack.built' AND e.merchant_id = :merchant
                  AND e.payload->>'pack_id' = p.pack_id"""),
        {
            "merchant": body.merchant_id,
            "case": body.case_id,
            "type": body.pack_type,
            "built": body.sim_at,
        },
    ).mappings().one_or_none()


def _validate_stored_artifacts(existing) -> tuple[Path, Path]:
    data = existing["data"] or {}
    json_disk = Path(data.get("json_path", ""))
    pdf_disk = Path(data.get("pdf_path", ""))
    root = pack_paths(existing["pack_id"])[0].parent.resolve()
    for path in (json_disk, pdf_disk):
        resolved = path.resolve()
        if not resolved.is_relative_to(root) or not resolved.is_file():
            raise HTTPException(
                500,
                "Recorded pack artifacts are missing or inconsistent; duplicate rebuild is not permitted.",
            )
    pdf_bytes = pdf_disk.read_bytes()
    if sha256_bytes(pdf_bytes) != existing["pdf_sha256"]:
        raise HTTPException(500, "Recorded pack PDF no longer matches its stored hash.")
    return json_disk, pdf_disk


def _response_from_existing(connection, existing, body: BuildPackRequest) -> BuildPackResponse:
    _validate_stored_artifacts(existing)
    _, _, json_path, pdf_path = pack_paths(existing["pack_id"])
    return BuildPackResponse(
        pack_id=existing["pack_id"],
        case_id=body.case_id,
        json_path=json_path,
        pdf_path=pdf_path,
        pdf_sha256=existing["pdf_sha256"],
        ledger_entry=wire_entry(
            LedgerEntry.model_validate(
                dict(
                    connection.execute(
                        text("SELECT * FROM ledger.entries WHERE seq = :seq AND merchant_id = :merchant"),
                        {"seq": existing["entry_seq"], "merchant": body.merchant_id},
                    ).mappings().one()
                )
            )
        ),
    )


def _lien_facts(case) -> tuple[str | None, int, date]:
    lien = (case["data"] or {}).get("lien") or {}
    raw_date = lien["disputed_date"]
    disputed_date = date.fromisoformat(raw_date) if isinstance(raw_date, str) else raw_date
    return lien.get("disputed_utr"), int(lien["disputed_amount"]), disputed_date


def _visible_case(connection, body: BuildPackRequest):
    return connection.execute(
        text("""SELECT * FROM ops.cases WHERE case_id = :case AND merchant_id = :merchant
                AND case_type = :type"""),
        {"case": body.case_id, "merchant": body.merchant_id, "type": body.pack_type},
    ).mappings().one_or_none()


def build_pack(connection, body: BuildPackRequest, role) -> BuildPackResponse:
    if body.pack_type == "notice":
        raise HTTPException(422, "Notice evidence packs are not supported until turnover/report skills exist.")
    validate_time(connection, body.sim_at)
    merchant(connection, body.merchant_id)
    lock_head(connection, body.merchant_id)

    case = _visible_case(connection, body)
    if case is None:
        raise HTTPException(404, f"No {body.pack_type} case {body.case_id} for this merchant.")
    if body.sim_at < case["opened_at"]:
        raise HTTPException(422, "A pack cannot be built before its case was opened.")

    existing = _existing_build(connection, body)
    if existing is not None:
        return _response_from_existing(connection, existing, body)

    disputed_utr, disputed_amount, disputed_date = _lien_facts(case)
    isolation = isolate(
        connection,
        IsolateRequest(
            merchant_id=body.merchant_id,
            case_id=body.case_id,
            disputed_utr=disputed_utr,
            disputed_amount=disputed_amount,
            disputed_date=disputed_date,
            date_window_days=1,
            as_of=body.sim_at,
        ),
    )

    pack_id = f"PACK-{uuid.uuid4().hex}"
    graded_amount = isolation.matched.amount if isolation.matched else 0
    if isolation.matched:
        tier_label, entry_refs = _tier_for_payment(
            connection,
            body.merchant_id,
            body.case_id,
            isolation.matched.txn_id,
            case["opened_at"],
            body.sim_at,
            isolation.bill,
        )
    else:
        tier_label, entry_refs = None, []
        opened_seq = _case_opened_seq(connection, body.merchant_id, body.case_id)
        if opened_seq is not None:
            entry_refs = [int(opened_seq)]

    tier_totals = _empty_tiers()
    grading = "ungraded"
    if tier_label and isolation.matched:
        tier_totals[tier_label] = {"amount": graded_amount, "count": 1}
        grading = f"tier_{tier_label}"

    profile = merchant(connection, body.merchant_id)
    lien = (case["data"] or {}).get("lien") or {}
    ledger_refs = _ledger_refs(connection, body.merchant_id, entry_refs)

    payload = {
        "stamp": "SYNTHETIC · SIMULATED · PROTOTYPE",
        "pack_id": pack_id,
        "case_id": body.case_id,
        "merchant_id": body.merchant_id,
        "business_name": profile.business_name,
        "case_opened_at_ist": _format_ist(case["opened_at"]),
        "pack_built_at_ist": _format_ist(body.sim_at),
        "lien": lien,
        "grading_scope": "Disputed payment only; full-period grading (6.1) is not implemented.",
        "grading": grading,
        "isolation": isolation.model_dump(mode="json"),
        "tier_totals": tier_totals,
        "ledger_evidence": ledger_refs,
    }

    json_disk, pdf_disk, json_path, pdf_path = pack_paths(pack_id)
    try:
        pdf_bytes = write_pdf(pdf_disk, pack_pdf_sections(payload, isolation, lien, profile.business_name))
        write_json(json_disk, payload)
    except Exception:
        for path in (json_disk, pdf_disk):
            if path.is_file():
                path.unlink()
        raise

    pdf_sha256 = sha256_bytes(pdf_bytes)
    pack_data = {
        "json_path": str(json_disk),
        "pdf_path": str(pdf_disk),
        "pdf_url": public_pdf_url(pack_id),
        "build_request": body.model_dump(mode="json"),
        "payload": payload,
    }
    entry = record_pack(
        connection,
        merchant_id=body.merchant_id,
        case_id=body.case_id,
        pack_id=pack_id,
        pack_type=body.pack_type,
        pdf_sha256=pdf_sha256,
        tier_totals=tier_totals,
        built_at=body.sim_at,
        data=pack_data,
    )
    return BuildPackResponse(
        pack_id=pack_id,
        case_id=body.case_id,
        json_path=json_path,
        pdf_path=pdf_path,
        pdf_sha256=pdf_sha256,
        ledger_entry=wire_entry(entry),
    )
