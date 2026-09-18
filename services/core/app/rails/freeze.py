"""Freeze detection: a lien opens the case, and WF20 is told once it is committed.

Plan §13 reads "a `lien_marked` event, **or** 3 or more `payment_declined` within 30 minutes
followed by lien confirmation, opens `case.opened(freeze)`". Both branches end at the lien, so
the lien is what opens the case; a qualifying burst in the 30 minutes before it is recorded on
the case as corroboration. Nothing opens a freeze case without a lien, because a burst of
declines on its own is an outage or a bank problem, not a freeze, and a case opened on one
would tell the merchant their money is held when it is not (D35).
"""

import json
import os
import urllib.error
import urllib.request
from datetime import timedelta

from sqlalchemy import text

from ..ledger.chain import append
from ..schemas.ledger import EntryKind
from ..schemas.roles import Role

DECLINE_WINDOW = timedelta(minutes=30)
DECLINE_BURST = 3


def case_id_for(event_id: str) -> str:
    """Derived from the trigger, so replaying the same lien cannot open a second case."""
    return f"CASE-FREEZE-{event_id}"


def open_case(connection, *, merchant_id, case_type, trigger_ref, sim_at, actor_role, actor_ref,
              case_id, data=None):
    """Insert the case and append `case.opened` in the caller's transaction.

    Returns (case_id, entry). The entry is None when this case already existed: rails replay is
    idempotent, and the chain refuses deletes, so a second `case.opened` could never be taken back.
    """
    inserted = connection.execute(
        text("""INSERT INTO ops.cases (case_id, merchant_id, case_type, trigger_ref, status, opened_at, data)
                VALUES (:case_id, :merchant, :case_type, :trigger, 'open', :sim_at, CAST(:data AS jsonb))
                ON CONFLICT (case_id) DO NOTHING RETURNING case_id"""),
        {"case_id": case_id, "merchant": merchant_id, "case_type": case_type,
         "trigger": trigger_ref, "sim_at": sim_at, "data": json.dumps(data or {})},
    ).scalar_one_or_none()
    if inserted is None:
        return case_id, None
    entry = append(connection, merchant_id=merchant_id, kind=EntryKind.CASE_OPENED,
                   actor_role=actor_role, actor_ref=actor_ref, sim_at=sim_at,
                   payload={"case_id": case_id, "case_type": case_type, "trigger_ref": trigger_ref})
    return case_id, entry


def decline_burst(connection, merchant_id, lien_ts):
    """Declines in the 30 minutes up to the lien, which is what the merchant actually felt."""
    rows = connection.execute(
        text("""SELECT event_id, ts FROM rails.events
                WHERE merchant_id = :merchant AND type = 'payment_declined'
                  AND ts <= :lien_ts AND ts >= :window_start ORDER BY ts"""),
        {"merchant": merchant_id, "lien_ts": lien_ts, "window_start": lien_ts - DECLINE_WINDOW},
    ).mappings().all()
    if len(rows) < DECLINE_BURST:
        return None
    return {"count": len(rows), "first_at": rows[0]["ts"].isoformat(),
            "last_at": rows[-1]["ts"].isoformat(), "event_ids": [row["event_id"] for row in rows]}


def detect(connection, event):
    """Open a freeze case for a lien. Returns WF20's webhook body, or None.

    The case is stamped with the lien's own time, not the time it was ingested. A replay loads
    events at its cutoff, so stamping the ingest time would date a 24 March freeze to whatever day
    the replay stopped, and every read before that day would miss the case.
    """
    if event.type != "lien_marked":
        return None
    burst = decline_burst(connection, event.merchant_id, event.ts)
    case_id, entry = open_case(
        connection, merchant_id=event.merchant_id, case_type="freeze", trigger_ref=event.event_id,
        sim_at=event.ts, actor_role=Role.RAILS, actor_ref="freeze-detector", case_id=case_id_for(event.event_id),
        data={"lien": {"event_id": event.event_id, "ts": event.ts.isoformat(),
                       "authority": event.authority.model_dump(mode="json"),
                       "case_ref": event.case_ref, "ncrp_ack": event.ncrp_ack,
                       "disputed_amount": event.disputed_amount, "disputed_utr": event.disputed_utr,
                       "disputed_date": event.disputed_date.isoformat()},
              "decline_burst": burst},
    )
    if entry is None:
        return None
    return {"case_id": case_id, "merchant_id": event.merchant_id, "opened_at": event.ts.isoformat(),
            "trigger": {"event_id": event.event_id, "type": event.type, "case_ref": event.case_ref,
                        "disputed_amount": event.disputed_amount, "disputed_utr": event.disputed_utr,
                        "decline_burst": burst}}


def notify(body):
    """Tell WF20. Best effort on purpose: the case is committed evidence and n8n is not.

    A freeze that reached the ledger must not be rolled back because the workflow engine is
    down, and WF20 polls for the officer decision anyway, so a missed webhook costs a retrigger,
    not the case.
    """
    url = os.getenv("N8N_FREEZE_WEBHOOK_URL", "http://n8n:5678/webhook/hisaab/wf20-freeze")
    request = urllib.request.Request(url, data=json.dumps(body).encode(), headers={
        "Content-Type": "application/json",
        "X-N8N-Webhook-Secret": os.getenv("N8N_WEBHOOK_SECRET", "dev-webhook-secret"),
    })
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            response.read()
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False
