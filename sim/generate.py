"""Generate the synthetic splits.

    python -m sim.generate                      # demo, dev, eval, sweep
    python -m sim.generate --only demo
    python -m sim.generate --out data --only demo --force

Writes data/<split>/{visible,hidden}/ plus data/<split>/manifest.json. Fixed seeds: the same code
gives byte-identical files. Product code reads visible/ only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sys
import time
from datetime import date, datetime
from pathlib import Path

from . import GENERATOR_VERSION
from . import catalog as C
from .notices import write_pdf, write_photo
from .scenario import LucknowScenario, SahanaScenario
from .validate import validate_split
from .world import MerchantSpec, Txn, World

FY = (C.FY_START, C.FY_END)
STATE_CODES = {"Karnataka": "29", "Uttar Pradesh": "09", "Tamil Nadu": "33", "Telangana": "36",
               "Maharashtra": "27", "West Bengal": "19"}

# merchant_id, archetype, difficulty, region, spec overrides, scenario
SPLITS = {
    "demo": dict(prefix="DM", seed=7, window=FY, merchants=[
        ("MID_DEMO_SAHANA", "demo_sahana", 0.45, "ka",
         dict(owner=("Sahana", "Gowda"), business_name="Sahana Stores", place_index=0,
              tax_notice=True, notice=SahanaScenario.NOTICE, onboarded_on=date(2023, 6, 12)),
         SahanaScenario),
        ("MID_DEMO_LKO", "demo_lucknow_veg", 0.35, "up",
         dict(owner=("Rakesh", "Maurya"), business_name="Maurya Sabzi Bhandar", place_index=0,
              tax_notice=True, notice=LucknowScenario.NOTICE, onboarded_on=date(2022, 11, 3)),
         LucknowScenario),
    ]),
    "dev": dict(prefix="DV", seed=101, window=FY, merchants=[
        ("DV_001", "veg_vendor", 0.3, "ka", dict(place_index=1, tax_notice=True, target_turnover=4_150_000), None),
        ("DV_002", "mixed_kirana", 0.4, "up", dict(place_index=1, tax_notice=True, target_turnover=5_200_000), None),
        ("DV_003", "family_kirana", 0.2, "tn", dict(target_turnover=3_850_000), None),
        ("DV_004", "family_kirana", 0.8, "ts", dict(fraud_freeze=True, target_turnover=3_940_000), None),
        ("DV_005", "mobile_accessories", 0.5, "mh", dict(lea_inquiry=True, target_turnover=5_800_000), None),
        ("DV_006", "darshini", 0.5, "ka", dict(place_index=2, target_turnover=4_600_000), None),
        ("DV_007", "composition_kirana", 0.4, "wb", dict(target_turnover=5_800_000), None),
    ]),
    "eval": dict(prefix="EV", seed=202, window=FY, merchants=[
        ("EV_001", "veg_vendor", 0.5, "up", dict(tax_notice=True, target_turnover=4_090_000), None),
        ("EV_002", "mixed_kirana", 0.7, "ka", dict(tax_notice=True, target_turnover=5_250_000), None),
        ("EV_003", "family_kirana", 0.3, "ts", dict(target_turnover=3_900_000), None),
        ("EV_004", "family_kirana", 0.9, "ka", dict(place_index=1, fraud_freeze=True, target_turnover=3_980_000), None),
        ("EV_005", "mobile_accessories", 0.2, "tn", dict(lea_inquiry=True, target_turnover=6_050_000), None),
        ("EV_006", "darshini", 0.6, "ka", dict(place_index=2, target_turnover=4_750_000), None),
        ("EV_007", "composition_kirana", 0.6, "mh", dict(target_turnover=5_950_000), None),
    ]),
    "sweep": dict(prefix="SW", seed=303, window=(date(2025, 10, 1), C.FY_END), merchants=[
        (f"SW_{int(d * 100):03d}", "family_kirana", d, "ka", {}, None)
        for d in (0.0, 0.25, 0.5, 0.75, 1.0)
    ]),
}


def iso(value):
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    raise TypeError(type(value))


def fmt_qty(q: float) -> str:
    return str(int(q)) if float(q).is_integer() else f"{q:g}"


def write_csv(path: Path, header: list[str], rows):
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(rows)


def write_json(path: Path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, default=iso) + "\n",
                    encoding="utf-8")


def build_worlds(name: str) -> list[World]:
    cfg = SPLITS[name]
    worlds = []
    for i, (mid, archetype, difficulty, region, extra, scenario) in enumerate(cfg["merchants"]):
        spec = MerchantSpec(mid, archetype, difficulty, region, seed=cfg["seed"] * 1000 + i,
                            window=cfg["window"], **extra)
        started = time.perf_counter()
        world = World(spec, scenario() if scenario else None).build()
        credits = sum(1 for t in world.txns if t.direction == "CR")
        print(f"  {mid:<16} {archetype:<20} d={difficulty:<4} {credits:>7,} credits "
              f"({time.perf_counter() - started:.1f}s)")
        worlds.append(world)
    return worlds


def assign_ids(prefix: str, worlds: list[World]):
    everything = sorted((t for w in worlds for t in w.txns),
                        key=lambda t: (t.ts, t.merchant_id, t.direction, t.amount, t.party.pid))
    for n, t in enumerate(everything, 1):
        t.txn_id = f"{prefix}{n:07d}"
        t.utr = f"{t.ts.year % 10}{t.ts.timetuple().tm_yday:03d}{t.ts.hour:02d}{n % 1_000_000:06d}"
    return everything


def ref(t: Txn) -> dict:
    return dict(txn_id=t.txn_id, utr=t.utr, ts=t.ts.isoformat(), amount=t.amount, channel=t.channel,
                payer=t.party.name, payer_handle=t.party.handle, true_label=t.label,
                billed=t.billed, reason=t.reason)


def write_split(name: str, worlds: list[World], out: Path):
    cfg = SPLITS[name]
    prefix = cfg["prefix"]
    visible, hidden = out / "visible", out / "hidden"
    (visible / "notices").mkdir(parents=True, exist_ok=True)
    hidden.mkdir(parents=True, exist_ok=True)
    txns = assign_ids(prefix, worlds)

    # ---------------------------------------------------------------- visible
    write_csv(visible / "transactions.csv",
              ["txn_id", "merchant_id", "ts", "direction", "amount", "channel", "counterparty_id",
               "counterparty_handle", "counterparty_name", "terminal_id", "pos_bill_id", "utr",
               "orig_txn_id", "note"],
              ([t.txn_id, t.merchant_id, t.ts.isoformat(), t.direction, t.amount, t.channel,
                t.party.pid, t.party.card if t.channel == "CARD_POS" else t.party.handle,
                t.party.name, t.terminal, f"B{t.txn_id}" if t.billed else "", t.utr,
                t.orig.txn_id if t.orig else "", t.note] for t in txns))

    bill_rows = []
    for t in txns:
        if t.billed:
            for i, line in enumerate(t.lines, 1):
                bill_rows.append([f"B{t.txn_id}", t.txn_id, t.merchant_id, i, line.item, line.hsn,
                                  fmt_qty(line.qty), line.unit, f"{line.amount / line.qty:.2f}",
                                  line.amount])
    write_csv(visible / "pos_bill_lines.csv",
              ["pos_bill_id", "txn_id", "merchant_id", "line_no", "item", "hsn", "qty", "unit",
               "rate", "line_amount"], bill_rows)

    merchants, terminals, balances = [], [], []
    for w in worlds:
        state_code = STATE_CODES[w.place["state"]]
        digest = hashlib.sha1(w.merchant_id.encode()).hexdigest().upper()
        merchants.append(dict(
            merchant_id=w.merchant_id, business_name=w.business_name, owner_name=w.owner_name,
            mcc=w.cfg["mcc"], category=w.cfg["category"], supply_kind=w.cfg["supply_kind"],
            gst_status=w.cfg["gst_status"],
            gstin=(f"{state_code}SYN{digest[:5]}{digest[5]}1Z{digest[6]}"
                   if w.cfg["gst_status"] != "unregistered" else None),
            locality=w.place["locality"], city=w.place["city"], state=w.place["state"],
            pincode=w.place["pincode"], geo=dict(lat=w.place["lat"], lon=w.place["lon"]),
            preferred_language=w.region["language"],
            terminals=[term["terminal_id"] for term in w.terminals],
            linked_own_accounts=[p.handle for p in w.own.values() if p.linked],
            settlement_account=w.settlement_account, onboarded_on=w.onboarded_on,
            data_window=[w.start, w.end],
        ))
        for term in w.terminals:
            tid = term["terminal_id"]
            h = hashlib.sha1(f"{w.merchant_id}|{tid}".encode()).hexdigest()
            jitter = (int(h[8:12], 16) / 65535 - 0.5) * 0.0008
            terminals.append(dict(
                merchant_id=w.merchant_id, terminal_id=tid, kind=term["kind"],
                device_id=f"{tid[:3]}-{h[:8].upper()}",
                model="Soundbox (synthetic)" if term["kind"] == "soundbox" else "Android POS (synthetic)",
                installed_at=w.onboarded_on,
                geo=dict(lat=round(w.place["lat"] + jitter, 6), lon=round(w.place["lon"] - jitter, 6)),
                address=f"{w.business_name}, {w.place['locality']}, {w.place['city']} {w.place['pincode']}",
            ))
        balances += [[w.merchant_id, b["date"].isoformat(), b["opening_balance"], b["credits"],
                      b["debits"], b["closing_balance"]] for b in w.balances]
    write_json(visible / "merchants.json", merchants)
    write_json(visible / "terminals.json", terminals)
    write_csv(visible / "daily_balances.csv",
              ["merchant_id", "date", "opening_balance", "credits", "debits", "closing_balance"],
              balances)
    write_json(visible / "hsn_catalog.json",
               [dict(item=r[0], hsn=r[1], exempt=r[2], basis=r[3], unit=r[5]) for r in C.ITEMS])

    notices_truth, events = [], []
    for w in worlds:
        for e in w.events:
            ev = dict(type=e["type"], merchant_id=w.merchant_id, ts=e["ts"])
            ev.update({k: v for k, v in e.items() if not k.startswith("_") and k not in ("type", "ts")})
            if "_disputed" in e:
                ev["disputed_utr" if e["type"] == "lien_marked" else "utr"] = e["_disputed"].utr
            if "_party" in e:
                p = e["_party"]
                ev.update(counterparty_id=p.pid, counterparty_name=p.name, counterparty_handle=p.handle)
            if e.get("_notice"):
                slug = w.notice["reference"].replace("/", "_")
                write_pdf(w.notice, visible / "notices" / f"{slug}.pdf")
                photo = write_photo(w.notice, visible / "notices" / f"{slug}.jpg")
                ev["document"] = f"notices/{slug}.pdf"
                ev["photo"] = f"notices/{slug}.jpg" if photo else None
                ev["note"] = ("The merchant received a paper notice and photographed it. Its contents "
                              "are only in the document.")
                notices_truth.append(dict(merchant_id=w.merchant_id, document=ev["document"],
                                          photo=ev["photo"], **{k: v for k, v in w.notice.items()}))
            events.append(ev)
    events.sort(key=lambda e: (e["ts"], e["merchant_id"]))
    for n, ev in enumerate(events, 1):
        ev_id = {"event_id": f"{prefix}E{n:05d}"}
        events[n - 1] = {**ev_id, **ev}
    write_json(visible / "rails_events.json", events)

    # ---------------------------------------------------------------- hidden
    credits = [t for t in txns if t.direction == "CR"]
    write_csv(hidden / "ground_truth.csv",
              ["txn_id", "merchant_id", "true_label", "reason", "exempt_value", "taxable_value",
               "counterparty_role", "counterparty_relation", "cues", "fraud_chain_id"],
              ([t.txn_id, t.merchant_id, t.label, t.reason, t.exempt_value, t.taxable_value,
                t.party.role, t.party.relation, ";".join(t.cues), t.fraud_chain_id] for t in credits))
    write_csv(hidden / "relationships.csv", ["txn_id", "related_txn_id", "relation"],
              sorted([a.txn_id, b.txn_id, rel] for w in worlds for a, b, rel in w.relationships))
    answers = {t: row for w in worlds for t, row in w.answers.items()}
    write_csv(hidden / "merchant_answers.csv",
              ["txn_id", "merchant_id", "true_label", "responds", "answer", "delay_minutes", "mode",
               "correction", "correction_lag_days"],
              ([t.txn_id, t.merchant_id, t.label, int(answers[t]["responds"]), answers[t]["answer"],
                answers[t]["delay_minutes"], answers[t]["mode"], answers[t]["correction"],
                answers[t]["correction_lag_days"]] for t in credits))
    write_json(hidden / "merchant_truth.json", [w.truth() for w in worlds])
    write_json(hidden / "behaviour.json", [w.behaviour for w in worlds])
    chains = []
    for w in worlds:
        for chain in w.fraud_chains:
            hops = []
            for hop in chain["hops"]:
                hop = dict(hop)
                if "credit" in hop:
                    credit = hop.pop("credit")
                    hop.update(txn_id=credit.txn_id, utr=credit.utr)
                hops.append(hop)
            chains.append({**chain, "hops": hops})
    write_json(hidden / "fraud_chains.json", chains)
    write_json(hidden / "notices_truth.json", notices_truth)
    scenarios = [s for s in (w.scenario.describe(w, ref) for w in worlds) if s]
    if scenarios:
        write_json(hidden / "demo_scenario.json", scenarios)

    # ---------------------------------------------------------------- manifest
    event_counts: dict[str, int] = {}
    for ev in events:
        event_counts[ev["type"]] = event_counts.get(ev["type"], 0) + 1
    write_json(out / "manifest.json", dict(
        generator="sim", generator_version=GENERATOR_VERSION, split=name, seed=cfg["seed"],
        txn_prefix=prefix, window=list(cfg["window"]),
        merchants=[w.merchant_id for w in worlds],
        counts=dict(transactions=len(txns), credits=len(credits), debits=len(txns) - len(credits),
                    pos_bill_lines=len(bill_rows), events=event_counts),
        rule="Product code reads visible/ only. hidden/ is for scoring, the demo answer key and the "
             "simulated-merchant harness.",
        visible=sorted(str(p.relative_to(visible)).replace("\\", "/")
                       for p in visible.rglob("*") if p.is_file()),
        hidden=sorted(p.name for p in hidden.iterdir()),
    ))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--only", choices=list(SPLITS), action="append",
                        help="generate only this split (repeatable)")
    parser.add_argument("--out", default="data", help="output root (default: data)")
    parser.add_argument("--force", action="store_true",
                        help="replace an existing split directory that was not made by this generator")
    args = parser.parse_args(argv)

    root = Path(args.out)
    for name in args.only or list(SPLITS):
        out = root / name
        if out.exists():
            manifest = out / "manifest.json"
            ours = manifest.exists() and json.loads(manifest.read_text(encoding="utf-8")).get("generator") == "sim"
            if not ours and not args.force and any(out.iterdir()):
                sys.exit(f"{out} exists and was not written by sim.generate; move it or pass --force")
            for child in out.iterdir():  # clear contents, keep the folder (Windows locks open dirs)
                shutil.rmtree(child) if child.is_dir() else child.unlink()
        print(f"{name}:")
        started = time.perf_counter()
        worlds = build_worlds(name)
        write_split(name, worlds, out)
        problems = validate_split(out)
        if problems:
            for p in problems:
                print(f"  INVALID  {p}")
            sys.exit(f"{name}: {len(problems)} validation problem(s)")
        print(f"  wrote {out} and validated it ({time.perf_counter() - started:.1f}s)")


if __name__ == "__main__":
    main()
