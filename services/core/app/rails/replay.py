"""Load a generated split's visible records up to a business-time cutoff."""

import csv
import json
import os
import re
from datetime import datetime, time
from pathlib import Path

from fastapi import HTTPException
from pydantic import TypeAdapter, ValidationError
from sqlalchemy import text

from ..clock import set_clock
from ..schemas.api.rails import PosBillLine, RailCreditTransaction, RailDebitTransaction, RailEvent
from ..schemas.api.reads import MerchantResponse
from .ingest import ingest_bills, ingest_events, ingest_transactions


def visible_directory(split):
    if not re.fullmatch(r"[a-zA-Z0-9_-]+", split):
        raise HTTPException(422, "Choose a generated split name, such as demo.")
    configured = os.getenv("HISAAB_DATA_DIR")
    root = Path(configured) if configured else Path(__file__).resolve().parents[4] / "data"
    directory = root / split / "visible"
    required = ("merchants.json", "terminals.json", "transactions.csv", "pos_bill_lines.csv", "rails_events.json", "hsn_catalog.json")
    if any(not (directory / name).is_file() for name in required):
        raise HTTPException(409, f"Generate the current {split} split first: python tasks.py generate --only {split} --force")
    return directory


def replay(connection, split, until):
    directory = visible_directory(split)
    try:
        merchants = [MerchantResponse.model_validate(item) for item in json.loads((directory / "merchants.json").read_text())]
        for merchant in merchants:
            connection.execute(text("""INSERT INTO rails.merchants (merchant_id, profile)
                VALUES (:merchant, CAST(:profile AS jsonb))
                ON CONFLICT (merchant_id) DO UPDATE SET profile = excluded.profile"""),
                {"merchant": merchant.merchant_id, "profile": merchant.model_dump_json()})
        for terminal in json.loads((directory / "terminals.json").read_text()):
            installed = datetime.fromisoformat(terminal["installed_at"])
            if installed.tzinfo is None:
                installed = datetime.combine(installed.date(), time(), until.tzinfo)
            if installed > until:
                continue
            connection.execute(text("""INSERT INTO rails.terminals (merchant_id, terminal_id, installed_at, data)
                VALUES (:merchant, :terminal, :installed, CAST(:data AS jsonb))
                ON CONFLICT (merchant_id, terminal_id) DO NOTHING"""),
                {"merchant": terminal["merchant_id"], "terminal": terminal["terminal_id"],
                 "installed": installed, "data": json.dumps(terminal)})
        catalog = json.loads((directory / "hsn_catalog.json").read_text())
        connection.execute(text("""INSERT INTO rails.hsn_catalog (item, hsn, exempt)
            VALUES (:item, :hsn, :exempt) ON CONFLICT (item, hsn) DO UPDATE SET exempt = excluded.exempt"""),
            [{key: item[key] for key in ("item", "hsn", "exempt")} for item in catalog])
        counts, observed = 0, {}
        with (directory / "transactions.csv").open(newline="") as handle:
            for row in csv.DictReader(handle):
                timestamp = datetime.fromisoformat(row["ts"])
                if timestamp > until:
                    continue
                row["amount"] = int(row["amount"])
                for key in ("terminal_id", "pos_bill_id", "orig_txn_id"):
                    row[key] = row[key] or None
                model = RailCreditTransaction if row["direction"] == "CR" else RailDebitTransaction
                transaction = model.model_validate(row)
                accepted, _ = ingest_transactions(connection, [transaction], timestamp, debit=row["direction"] == "DR")
                counts += accepted
                if row["direction"] == "CR":
                    observed[row["txn_id"]] = timestamp
        bills = {}
        with (directory / "pos_bill_lines.csv").open(newline="") as handle:
            for row in csv.DictReader(handle):
                if row["txn_id"] not in observed:
                    continue
                row["line_no"], row["line_amount"] = int(row["line_no"]), int(row["line_amount"])
                bills.setdefault(row["pos_bill_id"], []).append(PosBillLine.model_validate(row))
        for lines in bills.values():
            ingest_bills(connection, lines, observed[lines[0].txn_id])
        events = [TypeAdapter(RailEvent).validate_python(event)
                  for event in json.loads((directory / "rails_events.json").read_text())
                  if datetime.fromisoformat(event["ts"]) <= until]
        # Replay opens the freeze case a lien implies but does not start WF20: it is loading
        # history, and no other replayed record runs a workflow either.
        event_count, _ = ingest_events(connection, events, until)
        balances = directory / "daily_balances.csv"
        if balances.exists():
            initialized = set()
            with balances.open(newline="") as handle:
                for row in csv.DictReader(handle):
                    merchant = row["merchant_id"]
                    if merchant in initialized or row["date"] > until.date().isoformat():
                        continue
                    initialized.add(merchant)
                    connection.execute(text("""INSERT INTO ops.settings (key, data)
                        VALUES (:key, CAST(:data AS jsonb)) ON CONFLICT (key) DO NOTHING"""),
                        {"key": f"opening_balance:{merchant}", "data": json.dumps({"amount": int(row["opening_balance"])})})
    except (ValidationError, ValueError, KeyError) as exc:
        raise HTTPException(409, "Generated data does not match the current contracts; regenerate the split.") from exc
    set_clock(connection, until)
    return {"split": split, "sim_at": until, "transactions_replayed": counts, "events_replayed": event_count}
