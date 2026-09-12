"""Hisaab Data Service — FastAPI over data/<split>/visible + a SQLite provenance ledger.

Phinite tools run in Phinite's sandbox and cannot read our CSVs, so this service is
what they call. It deliberately holds no business logic: it serves rows and compact
rollups, and every judgment (labelling, projection, pack assembly) stays in the tools
where the Phinite trace can show the workings.

Run locally:
    .venv/bin/uvicorn service.app:app --reload --port 8000
"""
import os
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .store import DataError, Store

DATA_ROOT = os.getenv("HISAAB_DATA", "data")
SPLIT = os.getenv("HISAAB_SPLIT", "demo")
LEDGER_DB = os.getenv("HISAAB_LEDGER_DB", "ledger.db")
READ_KEY = os.getenv("HISAAB_KEY", "")
ATTEST_KEY = os.getenv("HISAAB_ATTEST_KEY", "")

app = FastAPI(
    title="Hisaab Data Service",
    version="0.1.0",
    description="Ledger storage for the Paytm Hisaab agent graphs.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

store: Store | None = None


@app.on_event("startup")
def _startup() -> None:
    global store
    store = Store(DATA_ROOT, SPLIT, LEDGER_DB)


def _store() -> Store:
    if store is None:
        raise HTTPException(503, "store not loaded")
    return store


# ---------- auth ----------
#
# The real permission boundary is the Phinite tool policy: Provenance is denied
# commit_attestation at the graph level. This is the second lock on the same door,
# so a mis-scoped tool cannot quietly attest on the merchant's behalf.


def require_read(x_hisaab_key: str = Header("")) -> str:
    if not READ_KEY and not ATTEST_KEY:
        return "open"
    if x_hisaab_key and x_hisaab_key in {READ_KEY, ATTEST_KEY}:
        return x_hisaab_key
    raise HTTPException(401, "bad or missing X-Hisaab-Key")


def require_attest(x_hisaab_key: str = Header("")) -> str:
    if not ATTEST_KEY:
        return "open"
    if x_hisaab_key == ATTEST_KEY:
        return x_hisaab_key
    raise HTTPException(
        403, "attestation requires HISAAB_ATTEST_KEY; only the Merchant graph holds it"
    )


# ---------- health ----------


@app.get("/health")
def health() -> dict:
    s = _store()
    return {
        "ok": True,
        "split": s.split,
        "merchants": len(s.merchants),
        "transactions": len(s.txns),
        "ledger_rows": s.db.execute("SELECT COUNT(*) FROM ledger").fetchone()[0],
        "auth": "open" if not (READ_KEY or ATTEST_KEY) else "keyed",
        "attest_key_set": bool(ATTEST_KEY),
        "served_at": datetime.now().isoformat(timespec="seconds"),
    }


# ---------- merchants ----------


@app.get("/merchants")
def merchants(_: str = Depends(require_read)) -> list[dict]:
    return list(_store().merchants.values())


@app.get("/merchants/{merchant_id}")
def merchant(merchant_id: str, _: str = Depends(require_read)) -> dict:
    m = _store().merchants.get(merchant_id)
    if m is None:
        raise HTTPException(404, f"no merchant {merchant_id}")
    return m


# ---------- credits ----------


@app.get("/credits")
def credits(
    merchant_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
    direction: str = Query("CR", pattern="^(CR|DR)$"),
    min_amount: int | None = None,
    max_amount: int | None = None,
    limit: int = Query(100, le=1000),
    offset: int = 0,
    _: str = Depends(require_read),
) -> dict:
    return _store().credits(
        merchant_id, date_from, date_to, direction, min_amount, max_amount, limit, offset
    )


@app.get("/credits/by_utr/{utr}")
def credit_by_utr(utr: str, _: str = Depends(require_read)) -> dict:
    row = _store().credit_by_utr(utr)
    if row is None:
        raise HTTPException(404, f"no transaction with UTR {utr}")
    return row


@app.get("/credits/{txn_id}")
def credit(txn_id: str, _: str = Depends(require_read)) -> dict:
    row = _store().credit(txn_id)
    if row is None:
        raise HTTPException(404, f"no transaction {txn_id}")
    return row


@app.get("/credits/{txn_id}/twins")
def twins(
    txn_id: str,
    window_minutes: int = 30,
    _: str = Depends(require_read),
) -> dict:
    s = _store()
    if txn_id not in s.by_txn_id:
        raise HTTPException(404, f"no transaction {txn_id}")
    return {
        "txn_id": txn_id,
        "twins": s.twins(txn_id, window_minutes),
        "refunds": s.refund_for(txn_id),
    }


# ---------- payer ----------


@app.get("/payer_history")
def payer_history(
    merchant_id: str,
    counterparty_id: str | None = None,
    txn_id: str | None = None,
    _: str = Depends(require_read),
) -> dict:
    s = _store()
    if counterparty_id is None:
        if txn_id is None:
            raise HTTPException(400, "pass counterparty_id or txn_id")
        txn = s.by_txn_id.get(txn_id)
        if txn is None:
            raise HTTPException(404, f"no transaction {txn_id}")
        counterparty_id = txn["counterparty_id"]
    return s.payer_history(merchant_id, counterparty_id)


# ---------- events ----------


@app.get("/events")
def events(
    merchant_id: str,
    type: str | None = None,
    _: str = Depends(require_read),
) -> list[dict]:
    return _store().merchant_events(merchant_id, type)


# ---------- reference ----------


@app.get("/hsn")
def hsn(_: str = Depends(require_read)) -> dict:
    return _store().hsn


# ---------- ledger ----------


class ProposeIn(BaseModel):
    txn_id: str
    label: str
    reason: str = ""
    confidence: float = Field(0.0, ge=0.0, le=1.0)


class AttestIn(BaseModel):
    txn_id: str
    label: str
    source: str = "merchant"
    note: str = ""


@app.get("/ledger")
def ledger(
    merchant_id: str,
    status: str | None = None,
    label: str | None = None,
    limit: int = Query(500, le=5000),
    offset: int = 0,
    _: str = Depends(require_read),
) -> dict:
    rows = _store().ledger(merchant_id, status, label, limit, offset)
    return {"count": len(rows), "rows": rows}


@app.get("/ledger/rollup")
def ledger_rollup(
    merchant_id: str,
    date_from: str | None = None,
    date_to: str | None = None,
    by_day: bool = False,
    _: str = Depends(require_read),
) -> dict:
    return _store().rollup(merchant_id, date_from, date_to, by_day)


@app.post("/ledger/propose")
def propose(body: ProposeIn, _: str = Depends(require_read)) -> dict:
    try:
        return _store().propose(
            body.txn_id, body.label, body.reason, body.confidence
        )
    except KeyError:
        raise HTTPException(404, f"no transaction {body.txn_id}")


@app.post("/ledger/attest")
def attest(body: AttestIn, _: str = Depends(require_attest)) -> dict:
    try:
        return _store().attest(body.txn_id, body.label, body.source, body.note)
    except KeyError:
        raise HTTPException(404, f"no transaction {body.txn_id}")


@app.get("/attestation_queue")
def attestation_queue(
    merchant_id: str,
    date: str,
    lookback_days: int = Query(1, ge=1, le=14),
    max: int = Query(3, ge=1, le=10),
    _: str = Depends(require_read),
) -> dict:
    q = _store().attestation_queue(merchant_id, date, lookback_days, max)
    return {"merchant_id": merchant_id, "asked_on": date, **q, "count": len(q["rows"])}


@app.exception_handler(DataError)
def _data_error(_request, exc: DataError):
    raise HTTPException(500, str(exc))
