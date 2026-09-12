"""Loads a split's visible/ data into memory and owns the provenance ledger.

Two rules this module exists to enforce:

1. `hidden/` is never opened. `_visible()` is the only path builder, and it refuses
   any path containing "hidden". That separation is what makes the accuracy number
   in DATA.md real.
2. The store aggregates, it does not decide. It returns rows and compact rollups;
   labelling, projection and pack logic all live in the Phinite tools so the
   workings show up in the trace.
"""
import csv
import json
import os
import sqlite3
import threading
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

IST = "+05:30"


def _parse_ts(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _day(ts: str) -> str:
    return ts[:10]


class DataError(RuntimeError):
    pass


class Store:
    def __init__(self, data_root: str, split: str, ledger_db: str):
        self.root = Path(data_root).resolve()
        self.split = split
        self.ledger_db = ledger_db
        self._lock = threading.Lock()
        self._load()
        self._init_ledger()

    # ---------- visible data ----------

    def _visible(self, name: str) -> Path:
        p = (self.root / self.split / "visible" / name).resolve()
        if "hidden" in p.parts:
            raise DataError(f"refusing to read hidden data: {p}")
        if not str(p).startswith(str(self.root)):
            raise DataError(f"path escapes data root: {p}")
        if not p.exists():
            raise DataError(
                f"{p} missing. Run: python -m synth.generate --only {self.split}"
            )
        return p

    def _load(self) -> None:
        with self._visible("transactions.csv").open() as fh:
            rows = list(csv.DictReader(fh))
        for r in rows:
            r["amount"] = int(r["amount"])
        self.txns = rows
        self.by_txn_id = {r["txn_id"]: r for r in rows}
        self.by_utr = {r["utr"]: r for r in rows if r["utr"]}

        self.credits_by_merchant = defaultdict(list)
        self.debits_by_merchant = defaultdict(list)
        for r in rows:
            bucket = (
                self.credits_by_merchant
                if r["direction"] == "CR"
                else self.debits_by_merchant
            )
            bucket[r["merchant_id"]].append(r)

        # counterparty -> their transactions, per merchant
        self.by_payer = defaultdict(list)
        for r in rows:
            if r["counterparty_id"]:
                self.by_payer[(r["merchant_id"], r["counterparty_id"])].append(r)

        with self._visible("pos_bill_lines.csv").open() as fh:
            lines = list(csv.DictReader(fh))
        for ln in lines:
            ln["line_amount"] = int(ln["line_amount"])
            ln["line_no"] = int(ln["line_no"])
        self.bill_lines = defaultdict(list)
        for ln in lines:
            self.bill_lines[ln["pos_bill_id"]].append(ln)

        with self._visible("merchants.json").open() as fh:
            self.merchants = {m["merchant_id"]: m for m in json.load(fh)}
        with self._visible("merchant_events.json").open() as fh:
            self.events = json.load(fh)

        ref = (self.root / "reference" / "hsn_catalog.json").resolve()
        self.hsn = json.loads(ref.read_text()) if ref.exists() else {}

    # ---------- ledger ----------

    def _init_ledger(self) -> None:
        self.db = sqlite3.connect(self.ledger_db, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute(
            """
            CREATE TABLE IF NOT EXISTS ledger (
                txn_id      TEXT PRIMARY KEY,
                merchant_id TEXT NOT NULL,
                label       TEXT NOT NULL,
                status      TEXT NOT NULL CHECK (status IN ('proposed','attested')),
                reason      TEXT,
                confidence  REAL,
                source      TEXT,
                note        TEXT,
                proposed_at TEXT,
                attested_at TEXT
            )
            """
        )
        self.db.execute(
            "CREATE INDEX IF NOT EXISTS ledger_merchant ON ledger (merchant_id, status)"
        )
        self.db.commit()

    def propose(
        self,
        txn_id: str,
        label: str,
        reason: str,
        confidence: float,
    ) -> dict:
        txn = self.by_txn_id.get(txn_id)
        if txn is None:
            raise KeyError(txn_id)
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            existing = self.db.execute(
                "SELECT status FROM ledger WHERE txn_id = ?", (txn_id,)
            ).fetchone()
            if existing and existing["status"] == "attested":
                # A proposal never overwrites a merchant's attestation.
                return self.ledger_row(txn_id)
            self.db.execute(
                """
                INSERT INTO ledger (txn_id, merchant_id, label, status, reason,
                                    confidence, proposed_at)
                VALUES (?, ?, ?, 'proposed', ?, ?, ?)
                ON CONFLICT(txn_id) DO UPDATE SET
                    label=excluded.label, status='proposed', reason=excluded.reason,
                    confidence=excluded.confidence, proposed_at=excluded.proposed_at
                """,
                (txn_id, txn["merchant_id"], label, reason, confidence, now),
            )
            self.db.commit()
        return self.ledger_row(txn_id)

    def attest(self, txn_id: str, label: str, source: str, note: str = "") -> dict:
        txn = self.by_txn_id.get(txn_id)
        if txn is None:
            raise KeyError(txn_id)
        now = datetime.now().isoformat(timespec="seconds")
        with self._lock:
            self.db.execute(
                """
                INSERT INTO ledger (txn_id, merchant_id, label, status, source, note,
                                    attested_at)
                VALUES (?, ?, ?, 'attested', ?, ?, ?)
                ON CONFLICT(txn_id) DO UPDATE SET
                    label=excluded.label, status='attested', source=excluded.source,
                    note=excluded.note, attested_at=excluded.attested_at
                """,
                (txn_id, txn["merchant_id"], label, source, note, now),
            )
            self.db.commit()
        return self.ledger_row(txn_id)

    def ledger_row(self, txn_id: str) -> dict | None:
        row = self.db.execute(
            "SELECT * FROM ledger WHERE txn_id = ?", (txn_id,)
        ).fetchone()
        return dict(row) if row else None

    def ledger(
        self,
        merchant_id: str,
        status: str | None = None,
        label: str | None = None,
        limit: int = 500,
        offset: int = 0,
    ) -> list[dict]:
        sql = "SELECT * FROM ledger WHERE merchant_id = ?"
        args: list = [merchant_id]
        if status:
            sql += " AND status = ?"
            args.append(status)
        if label:
            sql += " AND label = ?"
            args.append(label)
        sql += " ORDER BY txn_id LIMIT ? OFFSET ?"
        args += [limit, offset]
        return [dict(r) for r in self.db.execute(sql, args).fetchall()]

    def rollup(
        self,
        merchant_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
        by_day: bool = False,
    ) -> dict:
        """Sum attested-or-proposed amounts by label, with attested kept separate.

        The turnover tool needs to know which rupees a merchant actually stood
        behind, so attested and proposed never get added together here.
        """
        rows = self.db.execute(
            "SELECT txn_id, label, status FROM ledger WHERE merchant_id = ?",
            (merchant_id,),
        ).fetchall()
        by_label: dict = defaultdict(
            lambda: {
                "attested": {"count": 0, "amount": 0},
                "proposed": {"count": 0, "amount": 0},
            }
        )
        daily: dict = defaultdict(lambda: defaultdict(int))
        untagged = {"count": 0, "amount": 0}
        tagged_ids = set()

        for r in rows:
            txn = self.by_txn_id.get(r["txn_id"])
            if txn is None or txn["direction"] != "CR":
                continue
            d = _day(txn["ts"])
            if date_from and d < date_from:
                continue
            if date_to and d > date_to:
                continue
            tagged_ids.add(r["txn_id"])
            slot = by_label[r["label"]][r["status"]]
            slot["count"] += 1
            slot["amount"] += txn["amount"]
            if by_day:
                daily[d][r["label"]] += txn["amount"]

        for txn in self.credits_by_merchant.get(merchant_id, []):
            d = _day(txn["ts"])
            if date_from and d < date_from:
                continue
            if date_to and d > date_to:
                continue
            if txn["txn_id"] not in tagged_ids:
                untagged["count"] += 1
                untagged["amount"] += txn["amount"]

        out = {
            "merchant_id": merchant_id,
            "date_from": date_from,
            "date_to": date_to,
            "by_label": {k: dict(v) for k, v in by_label.items()},
            "untagged": untagged,
        }
        if by_day:
            out["by_day"] = {d: dict(v) for d, v in sorted(daily.items())}
        return out

    # ---------- reads ----------

    def credit(self, txn_id: str) -> dict | None:
        txn = self.by_txn_id.get(txn_id)
        if txn is None:
            return None
        return self._with_bill(txn)

    def credit_by_utr(self, utr: str) -> dict | None:
        txn = self.by_utr.get(utr)
        return self._with_bill(txn) if txn else None

    def _with_bill(self, txn: dict) -> dict:
        out = dict(txn)
        out["bill_lines"] = sorted(
            self.bill_lines.get(txn["pos_bill_id"], []),
            key=lambda ln: ln["line_no"],
        ) if txn["pos_bill_id"] else []
        out["ledger"] = self.ledger_row(txn["txn_id"])
        return out

    def credits(
        self,
        merchant_id: str,
        date_from: str | None = None,
        date_to: str | None = None,
        direction: str = "CR",
        min_amount: int | None = None,
        max_amount: int | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> dict:
        pool = (
            self.credits_by_merchant if direction == "CR" else self.debits_by_merchant
        ).get(merchant_id, [])
        sel = []
        for r in pool:
            d = _day(r["ts"])
            if date_from and d < date_from:
                continue
            if date_to and d > date_to:
                continue
            if min_amount is not None and r["amount"] < min_amount:
                continue
            if max_amount is not None and r["amount"] > max_amount:
                continue
            sel.append(r)
        total = len(sel)
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "rows": [dict(r) for r in sel[offset : offset + limit]],
        }

    def payer_history(self, merchant_id: str, counterparty_id: str) -> dict:
        """Compact aggregate for one counterparty. Aggregation only, no judgment."""
        rows = sorted(
            self.by_payer.get((merchant_id, counterparty_id), []),
            key=lambda r: r["ts"],
        )
        credits = [r for r in rows if r["direction"] == "CR"]
        debits = [r for r in rows if r["direction"] == "DR"]
        merchant = self.merchants.get(merchant_id, {})
        linked = set(merchant.get("linked_own_accounts", []))

        channels: dict = defaultdict(int)
        hours: dict = defaultdict(int)
        for r in credits:
            channels[r["channel"]] += 1
            hours[_parse_ts(r["ts"]).hour] += 1

        names = {r["counterparty_name"] for r in rows if r["counterparty_name"]}
        handles = {r["counterparty_handle"] for r in rows if r["counterparty_handle"]}

        amounts = [r["amount"] for r in credits]
        return {
            "merchant_id": merchant_id,
            "counterparty_id": counterparty_id,
            "names": sorted(names),
            "handles": sorted(handles),
            "credit_count": len(credits),
            "credit_total": sum(amounts),
            "credit_min": min(amounts) if amounts else None,
            "credit_max": max(amounts) if amounts else None,
            "first_seen": credits[0]["ts"] if credits else None,
            "last_seen": credits[-1]["ts"] if credits else None,
            "channels": dict(channels),
            "hour_histogram": dict(sorted(hours.items())),
            "merchant_has_paid_them": len(debits) > 0,
            "merchant_paid_count": len(debits),
            "merchant_paid_total": sum(r["amount"] for r in debits),
            "handle_is_linked_own_account": bool(handles & linked),
            "recent": [dict(r) for r in credits[-10:]],
        }

    def twins(self, txn_id: str, window_minutes: int = 30) -> list[dict]:
        """Same merchant, same payer, same amount, within a window. Duplicate evidence."""
        txn = self.by_txn_id.get(txn_id)
        if txn is None:
            return []
        t = _parse_ts(txn["ts"])
        span = timedelta(minutes=window_minutes)
        out = []
        for r in self.by_payer.get((txn["merchant_id"], txn["counterparty_id"]), []):
            if r["txn_id"] == txn_id or r["direction"] != "CR":
                continue
            if r["amount"] == txn["amount"] and abs(_parse_ts(r["ts"]) - t) <= span:
                out.append(dict(r))
        return sorted(out, key=lambda r: r["ts"])

    def refund_for(self, txn_id: str) -> list[dict]:
        """Refund / reversal rows pointing back at this transaction."""
        return [
            dict(r)
            for r in self.txns
            if r["orig_txn_id"] == txn_id
        ]

    def merchant_events(
        self, merchant_id: str, kind: str | None = None
    ) -> list[dict]:
        return [
            e
            for e in self.events
            if e["merchant_id"] == merchant_id and (kind is None or e["type"] == kind)
        ]

    def attestation_queue(
        self,
        merchant_id: str,
        day: str,
        lookback_days: int = 1,
        max_items: int = 3,
    ) -> list[dict]:
        """Proposals awaiting the merchant, least confident first, hard-capped.

        `day` is the day the agent is asking, and the window is the `lookback_days`
        days *before* it: the demo asks on 10 Mar about credits from 8-9 Mar, so a
        single-date filter would surface nothing.

        The cap is the product: PLAN says if the agent asks about more than ~3
        credits a day, nobody uses it.
        """
        asked_on = date.fromisoformat(day)
        window_from = (asked_on - timedelta(days=lookback_days)).isoformat()
        window_to = (asked_on - timedelta(days=1)).isoformat()

        rows = self.db.execute(
            "SELECT * FROM ledger WHERE merchant_id = ? AND status = 'proposed'",
            (merchant_id,),
        ).fetchall()
        out = []
        for r in rows:
            txn = self.by_txn_id.get(r["txn_id"])
            if txn is None or txn["direction"] != "CR":
                continue
            if not (window_from <= _day(txn["ts"]) <= window_to):
                continue
            item = self._with_bill(txn)
            item["proposal"] = dict(r)
            out.append(item)
        out.sort(key=lambda i: (i["proposal"]["confidence"] or 0.0, -i["amount"]))
        return {
            "window_from": window_from,
            "window_to": window_to,
            "pending_total": len(out),
            "rows": out[:max_items],
        }
