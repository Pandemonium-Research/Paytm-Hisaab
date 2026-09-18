"""6.10: the officer's decision on a pack, and an outbox that will not send without it.

The gate is the ledger, not `ops.approvals`. The application role may UPDATE ops working state,
so a status column can be flipped by anything holding that connection; the ledger refuses UPDATE
and DELETE outright. Whether a pack may be sent is therefore answered only from `pack.approved`
and `pack.rejected` entries appended by the officer role, and `ops.approvals` just mirrors them for
the screens (D37).
"""

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

from fastapi import HTTPException
from sqlalchemy import text

from ..ledger.chain import append, lock_head
from ..ledger.mutations import existing_entry, validate_time
from ..schemas.ledger import EntryKind
from ..schemas.roles import Role

log = logging.getLogger(__name__)

DECISION_KINDS = (EntryKind.PACK_APPROVED.value, EntryKind.PACK_REJECTED.value)


def delivery_ref_for(pack_id: str) -> str:
    """A pack is sent once, so its delivery is named after it."""
    return f"SIM-{pack_id}"


def pack(connection, pack_id):
    row = connection.execute(text("SELECT * FROM ops.packs WHERE pack_id = :pack"), {"pack": pack_id}).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, f"No evidence pack {pack_id}.")
    return row


def ledger_entries(connection, merchant_id, pack_id, kinds):
    rows = connection.execute(text("""SELECT seq FROM ledger.entries
        WHERE merchant_id = :merchant AND kind = ANY(:kinds) AND actor_role = :officer
          AND payload->>'pack_id' = :pack ORDER BY chain_index"""),
        {"merchant": merchant_id, "kinds": list(kinds), "officer": Role.OFFICER.value, "pack": pack_id}).scalars().all()
    return [existing_entry(connection, seq) for seq in rows]


def decide(connection, pack_id, body, role, *, approve):
    """Append the officer's one decision on a pack. Returns (entry, resume_url or None).

    A decision is final. An identical retry (a double tap, an n8n retry) returns the original entry;
    anything else is a 409, so a pack can never carry both an approval and a rejection.
    """
    validate_time(connection, body.sim_at)
    built = pack(connection, pack_id)
    # Serialises every write on this merchant's chain, so two officers deciding at once cannot both
    # see "no decision yet"; the second waits here and then finds the first one's entry.
    lock_head(connection, built["merchant_id"])
    if body.sim_at < built["built_at"]:
        raise HTTPException(422, "A pack cannot be decided before it was built.")
    kind = EntryKind.PACK_APPROVED if approve else EntryKind.PACK_REJECTED
    payload = {"pack_id": pack_id, "note": body.note} if approve else {"pack_id": pack_id, "reason": body.reason}
    approval = connection.execute(text("SELECT * FROM ops.approvals WHERE pack_id = :pack"), {"pack": pack_id}).mappings().one()
    resume_url = approval["resume_url"] if resume_allowed(approval["resume_url"]) else None
    previous = ledger_entries(connection, built["merchant_id"], pack_id, DECISION_KINDS)
    if previous:
        first = previous[0].root
        same = (first.kind == kind and first.payload.model_dump(mode="json") == payload
                and first.actor_ref == body.officer_ref and first.sim_at == body.sim_at)
        if not same:
            decided = "approved" if first.kind == EntryKind.PACK_APPROVED else "rejected"
            raise HTTPException(409, f"This pack was already {decided}; an officer's decision is final.")
        # Resume again on a retry: the first attempt may not have reached the workflow, and a Wait
        # that has already resumed ignores a second call.
        return previous[0], resume_url
    entry = append(connection, merchant_id=built["merchant_id"], kind=kind, actor_role=role,
                   actor_ref=body.officer_ref, sim_at=body.sim_at, payload=payload)
    connection.execute(text("""UPDATE ops.approvals SET status = :status, officer_ref = :officer,
                               data = data || CAST(:data AS jsonb) WHERE pack_id = :pack"""),
                       {"status": "approved" if approve else "rejected", "officer": body.officer_ref, "pack": pack_id,
                        "data": json.dumps({"decision_seq": entry.root.seq})})
    return entry, resume_url


def send(connection, pack_id, body, role):
    """Deliver an approved pack to its simulated destination. Returns (entry, delivery_ref).

    Nothing here touches the network: the prototype's delivery is a row in `ops.outbox` and a
    `pack.sent` entry, and every response says `simulated: true`.
    """
    validate_time(connection, body.sim_at)
    built = pack(connection, pack_id)
    lock_head(connection, built["merchant_id"])
    decisions = ledger_entries(connection, built["merchant_id"], pack_id, DECISION_KINDS)
    approvals = [entry for entry in decisions if entry.root.kind == EntryKind.PACK_APPROVED]
    if not approvals or len(approvals) != len(decisions):
        raise HTTPException(409, "Refused: this pack has no officer approval in the ledger, so it cannot be sent.")
    if body.sim_at < approvals[0].root.sim_at:
        raise HTTPException(422, "A pack cannot be sent before it was approved.")
    delivery_ref = delivery_ref_for(pack_id)
    sent = connection.execute(text("SELECT * FROM ops.outbox WHERE pack_id = :pack"), {"pack": pack_id}).mappings().one_or_none()
    if sent is not None:
        if sent["destination"] != body.destination:
            raise HTTPException(409, f"This pack was already sent to {sent['destination']}.")
        return existing_entry(connection, sent["data"]["entry_seq"]), delivery_ref
    entry = append(connection, merchant_id=built["merchant_id"], kind=EntryKind.PACK_SENT, actor_role=role,
                   actor_ref="outbox", sim_at=body.sim_at,
                   payload={"pack_id": pack_id, "destination": body.destination, "delivery_ref": delivery_ref})
    connection.execute(text("""INSERT INTO ops.outbox (delivery_id, pack_id, destination, simulated, data)
                               VALUES (:delivery, :pack, :destination, true, CAST(:data AS jsonb))"""),
                       {"delivery": delivery_ref, "pack": pack_id, "destination": body.destination,
                        "data": json.dumps({"entry_seq": entry.root.seq, "sim_at": body.sim_at.isoformat()})})
    connection.execute(text("UPDATE ops.approvals SET status = 'sent' WHERE pack_id = :pack"), {"pack": pack_id})
    return entry, delivery_ref


def n8n_origin():
    parsed = urllib.parse.urlsplit(os.getenv("N8N_BASE_URL", "http://n8n:5678"))
    return parsed.scheme, parsed.netloc


def resume_allowed(url):
    """Only our own n8n may be resumed. The call carries the webhook secret, and a resume URL
    stored by whoever built the pack must not be able to send that secret anywhere else."""
    if not url:
        return False
    parsed = urllib.parse.urlsplit(url)
    return (parsed.scheme, parsed.netloc) == n8n_origin()


def resume(url, body):
    """Resume the waiting workflow; runs after the decision has committed. Best effort.

    WF20 must re-read the decision from core rather than trust this body, so a lost resume costs a
    poll, not a wrong send.
    """
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json",
        "X-N8N-Webhook-Secret": os.getenv("N8N_WEBHOOK_SECRET", "dev-webhook-secret"),
    })
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            response.read()
        return True
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        log.warning("Could not resume the workflow for pack %s: %s", body.get("pack_id"), exc)
        return False
