"""Recording a built evidence pack, with the approval record its decision will need.

Rendering the pack (JSON and PDF) is 6.8's. This is the part the officer's decision depends on,
kept apart so 6.8's `POST /packs` records its packs exactly as the 6.10 tests do.
"""

import json

from fastapi import HTTPException
from sqlalchemy import text

from ..ledger.chain import append
from ..schemas.ledger import EntryKind
from ..schemas.roles import Role


def approval_id_for(pack_id: str) -> str:
    """One approval record per pack: a pack gets one final decision."""
    return f"APPROVAL-{pack_id}"


def record_pack(connection, *, merchant_id, case_id, pack_id, pack_type, pdf_sha256, tier_totals, built_at,
                resume_url=None, data=None):
    """Store the pack, open its approval as awaiting a decision, and append `pack.built`."""
    case = connection.execute(text("SELECT * FROM ops.cases WHERE case_id = :case AND merchant_id = :merchant"),
                              {"case": case_id, "merchant": merchant_id}).mappings().one_or_none()
    if case is None:
        raise HTTPException(404, f"No case {case_id} for this merchant.")
    if built_at < case["opened_at"]:
        raise HTTPException(422, "A pack cannot be built before its case was opened.")
    entry = append(connection, merchant_id=merchant_id, kind=EntryKind.PACK_BUILT, actor_role=Role.EVIDENCE,
                   actor_ref="packs", sim_at=built_at,
                   payload={"pack_id": pack_id, "pdf_sha256": pdf_sha256, "tier_totals": tier_totals})
    connection.execute(text("""INSERT INTO ops.packs (pack_id, case_id, merchant_id, pack_type, pdf_sha256, built_at, data)
                               VALUES (:pack, :case, :merchant, :type, :sha, :built_at, CAST(:data AS jsonb))"""),
                       {"pack": pack_id, "case": case_id, "merchant": merchant_id, "type": pack_type, "sha": pdf_sha256,
                        "built_at": built_at, "data": json.dumps({**(data or {}), "entry_seq": entry.root.seq})})
    connection.execute(text("""INSERT INTO ops.approvals (approval_id, pack_id, status, resume_url)
                               VALUES (:approval, :pack, 'awaiting_approval', :resume_url)"""),
                       {"approval": approval_id_for(pack_id), "pack": pack_id, "resume_url": resume_url})
    return entry
