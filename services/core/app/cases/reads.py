"""6.11: merchant and officer case read models at the sim clock cutoff."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import HTTPException
from sqlalchemy import text

from ..clock import sim_now
from ..ledger.projection import merchant
from ..ledger.verify import verify
from ..ops.screens import amount_text
from ..schemas.ledger import EntryKind
from ..schemas.roles import Role

DECISION_KINDS = (EntryKind.PACK_APPROVED.value, EntryKind.PACK_REJECTED.value)
OFFICER = Role.OFFICER.value
WEAK_TIER_KEYS = frozenset({"3", "4"})
IST = ZoneInfo("Asia/Kolkata")


def case_title(case_type: str) -> str:
    return "Payments on hold" if case_type == "freeze" else "Tax notice received"


def disputed_from_case(case) -> tuple[int | None, str | None]:
    if case["case_type"] == "freeze":
        amount = (case["data"].get("lien") or {}).get("disputed_amount")
        if amount is None:
            return None, None
        return int(amount), amount_text(int(amount))
    return None, None


def escalation_at(row) -> datetime:
    data = row["data"] or {}
    if data.get("sim_at"):
        return datetime.fromisoformat(data["sim_at"])
    return row["created_at"]


def escalation_reasons(connection, merchant_id: str, case_id: str, as_of: datetime) -> list[str]:
    rows = connection.execute(
        text("""SELECT data FROM ops.escalations
                WHERE merchant_id = :merchant AND data->>'case_id' = :case
                  AND coalesce((data->>'sim_at')::timestamptz, created_at) <= :as_of
                ORDER BY coalesce((data->>'sim_at')::timestamptz, created_at), escalation_id"""),
        {"merchant": merchant_id, "case": case_id, "as_of": as_of},
    ).mappings().all()
    reasons = []
    for row in rows:
        for reason in (row["data"] or {}).get("reasons") or []:
            if reason not in reasons:
                reasons.append(reason)
    return reasons


def latest_pack(connection, case_id: str, merchant_id: str, as_of: datetime):
    return connection.execute(
        text("""SELECT p.*, e.chain_index, e.payload AS built_payload, e.sim_at AS built_sim_at
                FROM ops.packs p
                JOIN ledger.entries e ON e.seq = (p.data->>'entry_seq')::bigint
                WHERE p.case_id = :case AND p.merchant_id = :merchant
                  AND e.merchant_id = p.merchant_id AND e.kind = :built_kind
                  AND e.payload->>'pack_id' = p.pack_id
                  AND p.built_at <= :as_of AND e.sim_at <= :as_of
                ORDER BY p.built_at DESC, e.chain_index DESC, p.pack_id DESC
                LIMIT 1"""),
        {"case": case_id, "merchant": merchant_id, "as_of": as_of,
         "built_kind": EntryKind.PACK_BUILT.value},
    ).mappings().one_or_none()


def pack_ledger_events(connection, merchant_id: str, pack_id: str, as_of: datetime, *, kinds):
    return connection.execute(
        text("""SELECT kind, sim_at, payload, chain_index, seq, actor_role
                FROM ledger.entries
                WHERE merchant_id = :merchant AND sim_at <= :as_of AND kind = ANY(:kinds)
                  AND actor_role = :officer
                  AND payload->>'pack_id' = :pack
                ORDER BY chain_index"""),
        {"merchant": merchant_id, "as_of": as_of, "kinds": list(kinds), "pack": pack_id,
         "officer": OFFICER},
    ).mappings().all()


def weak_evidence_share(tier_totals: dict | None) -> float:
    if not tier_totals:
        return 0.0
    total = sum(item["amount"] for item in tier_totals.values())
    if total <= 0:
        return 0.0
    weak = sum(
        item["amount"]
        for key, item in tier_totals.items()
        if str(key) in WEAK_TIER_KEYS
    )
    return weak / total


def derive_pack_status(events, *, escalated: bool) -> str:
    kinds = [row["kind"] for row in events]
    if EntryKind.PACK_REJECTED.value in kinds:
        return "rejected"
    if EntryKind.PACK_SENT.value in kinds:
        return "sent"
    if EntryKind.PACK_APPROVED.value in kinds:
        return "approved"
    if escalated:
        return "escalated"
    return "awaiting_approval"


def pack_status(connection, merchant_id: str, pack, as_of: datetime, case_id: str) -> str:
    if pack is None:
        reasons = escalation_reasons(connection, merchant_id, case_id, as_of)
        return "escalated" if reasons else "open"
    events = pack_ledger_events(
        connection,
        merchant_id,
        pack["pack_id"],
        as_of,
        kinds=(EntryKind.PACK_APPROVED.value, EntryKind.PACK_REJECTED.value, EntryKind.PACK_SENT.value),
    )
    escalated = bool(escalation_reasons(connection, merchant_id, case_id, as_of))
    return derive_pack_status(events, escalated=escalated)


def queue_visible(status: str) -> bool:
    return status in {"open", "awaiting_approval", "escalated"}


def tier_totals_for_pack(pack) -> dict | None:
    if pack is None:
        return None
    return pack["built_payload"]["tier_totals"]


def officer_row(connection, case, pack, profile_name: str, as_of: datetime) -> dict:
    disputed_amount, disputed_amount_text = disputed_from_case(case)
    tier_totals = tier_totals_for_pack(pack)
    return {
        "case_id": case["case_id"],
        "merchant_id": case["merchant_id"],
        "business_name": profile_name,
        "case_type": case["case_type"],
        "opened_at": case["opened_at"],
        "disputed_amount": disputed_amount,
        "disputed_amount_text": disputed_amount_text,
        "weak_evidence_share": weak_evidence_share(tier_totals),
        "escalation_reasons": escalation_reasons(connection, case["merchant_id"], case["case_id"], as_of),
    }


def tier_bands(tier_totals: dict | None) -> list[dict]:
    if not tier_totals:
        return []
    items = []
    for key in sorted(tier_totals, key=lambda item: int(item)):
        row = tier_totals[key]
        amount = row["amount"]
        items.append({"label": f"Tier {key}", "amount": amount, "amount_text": amount_text(amount)})
    return items


def timeline_for(connection, case, pack, merchant_id: str, as_of: datetime) -> list[str]:
    lines: list[tuple[datetime, str]] = [(case["opened_at"], "Case opened")]
    if pack:
        built_at = pack["built_sim_at"]
        lines.append((built_at, "Pack built"))
        for row in pack_ledger_events(
            connection,
            merchant_id,
            pack["pack_id"],
            as_of,
            kinds=DECISION_KINDS + (EntryKind.PACK_SENT.value,),
        ):
            if row["kind"] == EntryKind.PACK_APPROVED.value:
                note = (row["payload"] or {}).get("note")
                text_line = f"Approved: {note}" if note else "Approved"
                lines.append((row["sim_at"], text_line))
            elif row["kind"] == EntryKind.PACK_REJECTED.value:
                reason = (row["payload"] or {}).get("reason") or "Rejected"
                lines.append((row["sim_at"], f"Rejected: {reason}"))
            elif row["kind"] == EntryKind.PACK_SENT.value:
                lines.append((row["sim_at"], "Pack sent"))
    for row in connection.execute(
        text("""SELECT data, created_at FROM ops.escalations
                WHERE merchant_id = :merchant AND data->>'case_id' = :case
                  AND coalesce((data->>'sim_at')::timestamptz, created_at) <= :as_of"""),
        {"merchant": merchant_id, "case": case["case_id"], "as_of": as_of},
    ).mappings():
        at = escalation_at(row)
        for reason in (row["data"] or {}).get("reasons") or []:
            lines.append((at, f"Escalated: {reason}"))
    lines.sort(key=lambda item: (item[0], item[1]))
    return [f"{at.astimezone(IST):%d %b %Y, %H:%M} IST · {line}" for at, line in lines]


def pdf_url_for(pack) -> str | None:
    if pack is None:
        return None
    path = (pack.get("data") or {}).get("pdf_url")
    if isinstance(path, str) and path.startswith("/") and not path.startswith("//"):
        return path
    return None


def merchant_cases(connection, merchant_id: str) -> dict:
    merchant(connection, merchant_id)
    as_of = sim_now(connection)
    rows = connection.execute(
        text("""SELECT * FROM ops.cases
                WHERE merchant_id = :merchant AND opened_at <= :as_of
                  AND case_type IN ('freeze', 'notice')
                ORDER BY opened_at DESC, case_id DESC"""),
        {"merchant": merchant_id, "as_of": as_of},
    ).mappings().all()
    items = []
    for case in rows:
        pack = latest_pack(connection, case["case_id"], merchant_id, as_of)
        status = pack_status(connection, merchant_id, pack, as_of, case["case_id"])
        disputed_amount, disputed_amount_text = disputed_from_case(case)
        items.append(
            {
                "case_id": case["case_id"],
                "case_type": case["case_type"],
                "status": status,
                "opened_at": case["opened_at"],
                "title": case_title(case["case_type"]),
                "disputed_amount": disputed_amount,
                "disputed_amount_text": disputed_amount_text,
            }
        )
    return {"items": items}


def officer_queue(connection) -> dict:
    as_of = sim_now(connection)
    cases = connection.execute(
        text("""SELECT c.*, m.profile->>'business_name' AS business_name
                FROM ops.cases c
                JOIN rails.merchants m ON m.merchant_id = c.merchant_id
                WHERE c.opened_at <= :as_of AND c.case_type IN ('freeze', 'notice')
                ORDER BY c.opened_at DESC, c.case_id DESC"""),
        {"as_of": as_of},
    ).mappings().all()
    items = []
    for case in cases:
        pack = latest_pack(connection, case["case_id"], case["merchant_id"], as_of)
        status = pack_status(connection, case["merchant_id"], pack, as_of, case["case_id"])
        if not queue_visible(status):
            continue
        items.append(officer_row(connection, case, pack, case["business_name"], as_of))
    return {"items": items}


def officer_case(connection, case_id: str) -> dict:
    as_of = sim_now(connection)
    case = connection.execute(text("SELECT * FROM ops.cases WHERE case_id = :case"), {"case": case_id}).mappings().one_or_none()
    if case is None or case["opened_at"] > as_of or case["case_type"] not in {"freeze", "notice"}:
        raise HTTPException(404, f"No case {case_id}.")
    profile = merchant(connection, case["merchant_id"])
    pack = latest_pack(connection, case_id, case["merchant_id"], as_of)
    status = pack_status(connection, case["merchant_id"], pack, as_of, case_id)
    built_payload = tier_totals_for_pack(pack)
    row = officer_row(connection, case, pack, profile.business_name, as_of)
    chain = verify(connection, case["merchant_id"])
    return {
        "case": row,
        "pack_id": pack["pack_id"] if pack else None,
        "status": status,
        "timeline": timeline_for(connection, case, pack, case["merchant_id"], as_of),
        "tier_totals": tier_bands(built_payload),
        "chain_ok": chain.ok,
        "pdf_url": pdf_url_for(pack),
    }


def usable_balance_at(connection, merchant_id: str, as_of: datetime) -> dict:
    freeze = connection.execute(
        text("""SELECT 1 FROM ops.cases
                WHERE merchant_id = :merchant AND case_type = 'freeze'
                  AND opened_at <= :as_of LIMIT 1"""),
        {"merchant": merchant_id, "as_of": as_of},
    ).scalar_one_or_none()
    if freeze:
        # A delivery records no bank release. Do not infer one from mutable case status.
        return {"amount": 0, "amount_text": amount_text(0)}
    sums = connection.execute(
        text("""SELECT
            coalesce((SELECT sum(amount) FROM rails.credits WHERE merchant_id = :merchant AND ts <= :as_of), 0) AS received,
            coalesce((SELECT sum(amount) FROM rails.debits WHERE merchant_id = :merchant AND ts <= :as_of), 0) AS paid"""),
        {"merchant": merchant_id, "as_of": as_of},
    ).mappings().one()
    opening = connection.execute(
        text("SELECT data FROM ops.settings WHERE key = :key"),
        {"key": f"opening_balance:{merchant_id}"},
    ).scalar_one_or_none()
    amount = max(0, (opening or {}).get("amount", 0) + int(sums["received"]) - int(sums["paid"]))
    return {"amount": amount, "amount_text": amount_text(amount)}


def officer_outbox(connection) -> dict:
    as_of = sim_now(connection)
    rows = connection.execute(
        text("""SELECT o.*, p.case_id, p.merchant_id, built.sim_at AS built_at,
                       c.opened_at AS freeze_at, m.profile->>'business_name' AS business_name,
                       sent.sim_at AS sent_sim_at, sent.payload AS sent_payload
                FROM ops.outbox o
                JOIN ops.packs p ON p.pack_id = o.pack_id
                JOIN ops.cases c ON c.case_id = p.case_id AND c.merchant_id = p.merchant_id
                JOIN rails.merchants m ON m.merchant_id = p.merchant_id
                JOIN ledger.entries built ON built.seq = (p.data->>'entry_seq')::bigint
                JOIN ledger.entries sent ON sent.seq = (o.data->>'entry_seq')::bigint
                WHERE sent.sim_at <= :as_of AND sent.kind = :sent_kind AND sent.actor_role = :officer
                  AND sent.merchant_id = p.merchant_id AND sent.payload->>'pack_id' = p.pack_id
                  AND built.merchant_id = p.merchant_id AND built.payload->>'pack_id' = p.pack_id
                  AND built.kind = :built_kind AND built.sim_at <= sent.sim_at
                  AND p.built_at <= :as_of AND c.opened_at <= built.sim_at
                  AND c.case_type IN ('freeze', 'notice')
                ORDER BY sent.sim_at DESC, o.pack_id DESC"""),
        {"as_of": as_of, "sent_kind": EntryKind.PACK_SENT.value,
         "built_kind": EntryKind.PACK_BUILT.value, "officer": OFFICER},
    ).mappings().all()
    items = []
    for row in rows:
        pack_id = row["pack_id"]
        merchant_id = row["merchant_id"]
        approved = connection.execute(
            text("""SELECT sim_at FROM ledger.entries
                    WHERE merchant_id = :merchant AND kind = :approved AND actor_role = :officer
                      AND payload->>'pack_id' = :pack AND sim_at <= :as_of
                      AND sim_at >= :built_at AND sim_at <= :sent_at
                      AND NOT EXISTS (
                        SELECT 1 FROM ledger.entries r
                        WHERE r.merchant_id = :merchant AND r.kind = :rejected AND r.actor_role = :officer
                          AND r.payload->>'pack_id' = :pack AND r.sim_at <= :as_of)
                    ORDER BY chain_index LIMIT 1"""),
            {
                "merchant": merchant_id,
                "approved": EntryKind.PACK_APPROVED.value,
                "rejected": EntryKind.PACK_REJECTED.value,
                "officer": OFFICER,
                "pack": pack_id,
                "as_of": as_of,
                "built_at": row["built_at"],
                "sent_at": row["sent_sim_at"],
            },
        ).scalar_one_or_none()
        if approved is None:
            continue
        freeze_at = row["freeze_at"]
        pack_built_at = row["built_at"]
        sent_at = row["sent_sim_at"]
        freeze_to_pack = max(0, int((pack_built_at - freeze_at).total_seconds()))
        pack_to_approval = max(0, int((approved - pack_built_at).total_seconds()))
        payload = row["sent_payload"] or {}
        items.append(
            {
                "pack_id": pack_id,
                "case_id": row["case_id"],
                "merchant_id": merchant_id,
                "business_name": row["business_name"],
                "destination": payload["destination"],
                "delivery_ref": payload["delivery_ref"],
                "status": "sent",
                "outcome": (row["data"] or {}).get("outcome"),
                "simulated": row["simulated"],
                "freeze_at": freeze_at,
                "pack_built_at": pack_built_at,
                "approved_at": approved,
                "sent_at": sent_at,
                "freeze_to_pack_seconds": freeze_to_pack,
                "pack_to_approval_seconds": pack_to_approval,
                "usable_balance": usable_balance_at(connection, merchant_id, sent_at),
            }
        )
    return {"items": items}
