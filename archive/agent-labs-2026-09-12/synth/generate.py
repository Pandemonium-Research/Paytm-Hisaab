"""Build the synthetic datasets for Paytm Hisaab.

    python -m synth.generate              # demo, dev, eval, sweep -> data/
    python -m synth.generate --only demo

Each split is written as data/<split>/visible (what the system under test may read)
and data/<split>/hidden (generator truth, for the scorer and the demo script only).
"""
import argparse
import csv
import json
import random
import shutil
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta
from pathlib import Path

from . import catalog as C
from .world import TRUE_LABELS, MerchantSim, World, at, crossing, is_sale

ROOT = Path(__file__).resolve().parent.parent / "data"
FY_START, FY_END = date(2025, 4, 1), date(2026, 3, 31)
DEMO_CROSS = date(2026, 3, 14)
SEEDS = {"demo": 7, "dev": 101, "eval": 202, "sweep": 303}
TAGS = {"demo": "DM", "dev": "DV", "eval": "EV", "sweep": "SW"}
SPLITS = {  # (archetype, difficulty); dev and eval differ in seed and difficulty
    "dev": [("veg_vendor", 0.3), ("mixed_kirana", 0.4), ("family_kirana", 0.2), ("family_kirana", 0.8),
            ("mobile_accessories", 0.5), ("darshini", 0.5), ("composition_kirana", 0.4)],
    "eval": [("veg_vendor", 0.5), ("mixed_kirana", 0.7), ("family_kirana", 0.3), ("family_kirana", 0.9),
             ("mobile_accessories", 0.2), ("darshini", 0.6), ("composition_kirana", 0.6)],
    "sweep": [("family_kirana", d) for d in (0.0, 0.25, 0.5, 0.75, 1.0)],
}
LEAS = [("Hyderabad", "Telangana"), ("Jaipur", "Rajasthan"), ("Lucknow", "Uttar Pradesh"), ("Ahmedabad", "Gujarat")]
TXN_COLS = ["txn_id", "merchant_id", "ts", "direction", "amount", "channel", "counterparty_id",
            "counterparty_handle", "counterparty_name", "terminal_id", "pos_bill_id", "utr", "orig_txn_id", "note"]
GT_COLS = ["txn_id", "merchant_id", "true_label", "reason", "exempt_value", "taxable_value",
           "counterparty_role", "counterparty_relation", "cues", "fraud_chain_id"]


def iso(ts):
    return ts.isoformat() + "+05:30"


def threshold(m):
    return 2_000_000 if m.a["kind"] == "services" else 4_000_000


def fy_quarter(d):
    fy = d.year if d.month >= 4 else d.year - 1
    return f"FY{fy}-{str(fy + 1)[2:]} Q{(d.month - 4) % 12 // 3 + 1}"


# ---- scenario seeding ---------------------------------------------------------------
def seed_fraud(w, m, amount, ts):
    rng = w.rng
    city, state = rng.choice(LEAS)
    freeze = datetime.combine(ts.date() + timedelta(days=rng.randint(2, 5)), time(9, 30))
    lea = dict(city=city, state=state, ncrp_ack=f"SYN-{rng.randint(10**13, 10**14 - 1)}",
               case_ref=f"SYN Cr. No. {rng.randint(100, 999)}/2026")
    return m.inject_fraud(ts, amount, f"FC_{w.tag}_{len(w.chains) + 1:03d}", freeze, lea)


def tax_notice(w, m, ref_no):
    gross = sum(r["amount"] for r in m.rows if r["direction"] == "CR")
    w.events.append(dict(
        type="tax_notice", merchant_id=m.mid, date="2026-08-20", reference=ref_no,
        authority="Commercial Taxes Department, Karnataka (synthetic)", period="FY 2025-26",
        basis="Digital (UPI / card) receipts reported by payment intermediaries",
        claimed_turnover=gross,
        allegation="Receipts exceed the registration threshold; the trader has not registered. "
                   "Tax, interest and penalty proposed on the full amount of receipts.",
    ))
    return gross


def declared_returns(w, m):
    per_q = defaultdict(int)
    for r in m.rows:
        if is_sale(r):
            per_q[fy_quarter(r["ts"].date())] += r["_exempt"] + r["_taxable"]
    m.declared = []
    for q, true_v in sorted(per_q.items()):
        declared = int(round(true_v * (1.0 if w.rng.random() < 0.5 else w.rng.uniform(0.7, 0.92)), -2))
        w.events.append(dict(type="declared_return", form="CMP-08", merchant_id=m.mid, period=q,
                             declared_turnover=declared))
        m.declared.append(dict(period=q, declared=declared, true_aggregate_turnover=true_v))


def build_split(name):
    w = World(random.Random(SEEDS[name]), TAGS[name])
    start = date(2025, 10, 1) if name == "sweep" else FY_START
    for i, (arch, d) in enumerate(SPLITS[name], 1):
        m = MerchantSim(w, f"MID_{w.tag}_{i:03d}", arch, d, start, FY_END)
        m.gen_sales()
        if name != "sweep" and arch == "family_kirana" and d > 0.5:
            day = w.rng.choice(m.days[-90:-7])
            seed_fraud(w, m, w.rng.choice((2750, 3600, 4200, 5100, 6480)), at(day, m.shop_hour(), w.rng))
        m.gen_rest()
        if m.a["gst"] == "composition":
            declared_returns(w, m)
        if arch == "mixed_kirana":
            tax_notice(w, m, f"SYN/CTD/2026-27/{w.rng.randint(1000, 9999):05d}")
    return w, None


def build_demo():
    w = World(random.Random(SEEDS["demo"]), TAGS["demo"])
    m = MerchantSim(w, "MID_DEMO_SAHANA", "demo_sahana", 0.45, FY_START, FY_END,
                    owner=("Sahana", "Gowda", "F"), business="Sahana Stores")
    m.locality = "Jayanagar"
    spouse = m.family[0]
    spouse.first, spouse.surname, spouse.name = "Manjunath", "Gowda", "MANJUNATH GOWDA"
    spouse.handle = "manjunath.gowda56@okhdfcbank"
    m.gen_sales()

    # Beat 1: three credits from Sun 8 / Mon 9 Mar, surfaced for attestation on Tue 10 Mar.
    raghu = w.person("customer", "tiffin-cart owner, occasional bulk buyer", "Shetty", "M", "Raghu")
    m.exact_sale(datetime(2026, 1, 24, 7, 12, 5), raghu, 2300, "UPI_QR")
    m.exact_sale(datetime(2026, 2, 17, 7, 40, 33), raghu, 3100, "UPI_QR")
    beat1 = [
        m.transfer(datetime(2026, 3, 8, 23, 4, 12), m.own[0], 15000, "inter_account",
                   "own_savings_topup_late_night", "UPI_INTENT"),
        m.transfer(datetime(2026, 3, 9, 13, 20, 41), spouse, 7500, "personal_transfer",
                   "spouse_household_transfer", "UPI_QR"),
        m.exact_sale(datetime(2026, 3, 9, 16, 40, 2), raghu, 4850, "UPI_QR"),
    ]

    # Beat 4: a Rs 4,200 sale to a layer-2 mule, plus an innocent same-amount decoy that week.
    fraud, _ = m.inject_fraud(datetime(2026, 3, 21, 19, 47, 5), 4200, "FC_DM_001", datetime(2026, 3, 24, 9, 30),
                              dict(city="Hyderabad", state="Telangana", ncrp_ack="SYN-31703260045812",
                                   case_ref="SYN Cr. No. 412/2026"))
    decoy = m.exact_sale(datetime(2026, 3, 18, 18, 22, 40), m.customers[3], 4200, "UPI_QR",
                         "regular_customer_purchase")

    # Beat 2: scale ordinary sales so aggregate turnover crosses Rs 40L on DEMO_CROSS.
    sales = [r for r in m.rows if is_sale(r)]

    def through(pinned, day):
        return sum(r["_exempt"] + r["_taxable"] for r in sales if r["_pinned"] == pinned and r["ts"].date() <= day)

    prev = DEMO_CROSS - timedelta(days=1)
    free_mid = (through(False, prev) + through(False, DEMO_CROSS)) / 2
    pin_mid = (through(True, prev) + through(True, DEMO_CROSS)) / 2
    m.calibrate((4_000_000 - pin_mid) / free_mid)
    m.gen_rest()

    # Keep beat 1 clean: nothing else non-sale on 8-9 Mar competes for the merchant's attention.
    keep = {id(r) for r in beat1}
    quiet = (date(2026, 3, 8), date(2026, 3, 9))
    m.drop([r for r in m.rows if r["direction"] == "CR" and not is_sale(r)
            and id(r) not in keep and r["ts"].date() in quiet])
    assert crossing(m.rows, 4_000_000) == DEMO_CROSS, crossing(m.rows, 4_000_000)

    gross = tax_notice(w, m, "SYN/CTD/2026-27/00417")
    merchant_truth(m)
    freeze_day = date(2026, 3, 24)
    week = [r for r in m.rows if r["direction"] == "CR" and freeze_day - timedelta(days=7) <= r["ts"].date() < freeze_day]
    t = m.truth
    scenario = dict(
        merchant_id=m.mid, business_name=m.business_name, owner=m.owner_name, language="kn",
        beat1_ordinary_tuesday=dict(
            attestation_date="2026-03-10",
            seeded_credits=beat1,
            intent="own savings at 11pm Sunday (inter_account); spouse on a weekday afternoon via QR "
                   "(personal_transfer, ambiguous); Rs 4,850 bulk sale from a payer seen twice before "
                   "(a sale the agent should ask about, not a transfer)",
        ),
        beat2_threshold=dict(
            threshold=4_000_000, true_crossing_date=DEMO_CROSS, replay_as_of="2026-01-31",
            basis="aggregate turnover = taxable + exempt supplies (CGST Act s.2(6)); excludes "
                  "personal, inter-account, non-business, duplicates and refunds",
        ),
        beat3_notice=dict(
            claimed_turnover=gross,
            true_breakdown={k: v["amount"] for k, v in t["by_label"].items()},
            exempt_turnover=t["exempt_turnover"], taxable_turnover=t["taxable_turnover"],
            aggregate_turnover=t["aggregate_turnover"],
        ),
        beat4_freeze=dict(
            freeze_ts="2026-03-24T09:30:00+05:30", disputed_credit=fraud, decoy_same_amount=decoy,
            credits_in_7_days_before_freeze=len(week),
        ),
    )
    return w, scenario


# ---- truth & writing ----------------------------------------------------------------
def merchant_truth(m):
    by = {lab: dict(count=0, amount=0) for lab in TRUE_LABELS}
    for r in m.rows:
        if r["direction"] == "CR":
            by[r["_label"]]["count"] += 1
            by[r["_label"]]["amount"] += r["amount"]
    ex = sum(r["_exempt"] for r in m.rows if is_sale(r))
    tx = sum(r["_taxable"] for r in m.rows if is_sale(r))
    full_fy = m.start == FY_START and m.end == FY_END
    cross = crossing(m.rows, threshold(m)) if full_fy else None
    m.truth = dict(
        archetype=m.arch_name, difficulty=m.d, supply_kind=m.a["kind"], gst_status=m.a["gst"],
        window=[m.start, m.end], gross_credits=sum(v["amount"] for v in by.values()), by_label=by,
        exempt_turnover=ex, taxable_turnover=tx, aggregate_turnover=ex + tx,
        registration_threshold=threshold(m), exclusively_exempt=tx == 0,
        threshold_crossing_date=cross,
        registration_required=(m.a["gst"] == "unregistered" and tx > 0 and cross is not None) if full_fy else None,
        own_accounts=[dict(pid=p.pid, handle=p.handle, name=p.name, relation=p.relation,
                           linked_in_profile=p.handle in m.linked_own) for p in m.own],
        family=[dict(pid=p.pid, handle=p.handle, name=p.name, relation=p.relation) for p in m.family],
        suppliers=[dict(pid=p.pid, name=p.name) for p in m.suppliers],
        declared_returns=getattr(m, "declared", None),
        fraud_chains=[c["chain_id"] for c in m.w.chains if c["merchant_id"] == m.mid],
    )


def ref(r):
    return dict(txn_id=r["txn_id"], utr=r["utr"], ts=iso(r["ts"]), amount=r["amount"], channel=r["channel"],
                counterparty=r["party"].name, true_label=r["_label"], reason=r["_reason"])


def resolve(o):
    """Make JSON-safe: rows become references, hidden (_-prefixed) keys are dropped."""
    if isinstance(o, dict):
        return ref(o) if "_m" in o else {k: resolve(v) for k, v in o.items() if not k.startswith("_")}
    if isinstance(o, (list, tuple)):
        return [resolve(v) for v in o]
    if isinstance(o, date):
        return o.isoformat()
    return o


def dump(path, obj):
    path.write_text(json.dumps(resolve(obj), indent=2, ensure_ascii=False), encoding="utf-8")


def write_split(w, name, scenario):
    out = ROOT / name
    if out.exists():
        shutil.rmtree(out)
    vis, hid = out / "visible", out / "hidden"
    vis.mkdir(parents=True)
    hid.mkdir()
    rows = sorted((r for m in w.merchants for r in m.rows), key=lambda r: (r["ts"], r["direction"]))
    for i, r in enumerate(rows, 1):
        ts = r["ts"]
        r["txn_id"] = f"{w.tag}{i:07d}"
        r["utr"] = f"{ts.year % 10}{ts.timetuple().tm_yday:03d}{ts.hour:02d}{i % 10**6:06d}"

    with open(vis / "transactions.csv", "w", newline="", encoding="utf-8") as ft, \
            open(vis / "pos_bill_lines.csv", "w", newline="", encoding="utf-8") as fb, \
            open(hid / "ground_truth.csv", "w", newline="", encoding="utf-8") as fg:
        tw, bw, gw = csv.writer(ft), csv.writer(fb), csv.writer(fg)
        tw.writerow(TXN_COLS)
        bw.writerow(["pos_bill_id", "txn_id", "merchant_id", "line_no", "item", "hsn", "line_amount"])
        gw.writerow(GT_COLS)
        n_bills = 0
        for r in rows:
            mid, p, bill_id = r["_m"].mid, r["party"], ""
            if r["bill"]:
                n_bills += 1
                bill_id = f"B{w.tag}{n_bills:07d}"
                for n, (item, hsn, v) in enumerate(r["bill"], 1):
                    bw.writerow([bill_id, r["txn_id"], mid, n, item, hsn, v])
            tw.writerow([r["txn_id"], mid, iso(r["ts"]), r["direction"], r["amount"], r["channel"], p.pid,
                         p.handle, p.name, r["terminal"], bill_id, r["utr"],
                         r["orig"]["txn_id"] if r["orig"] else "", r["note"]])
            if r["direction"] == "CR":
                gw.writerow([r["txn_id"], mid, r["_label"], r["_reason"], r["_exempt"], r["_taxable"],
                             p.role, p.relation, r["_cues"], r["_fraud"]])

    with open(hid / "relationships.csv", "w", newline="", encoding="utf-8") as f:
        rw = csv.writer(f)
        rw.writerow(["txn_id", "related_txn_id", "relation"])
        for m in w.merchants:
            for a, b, rel in sorted(m.rels, key=lambda x: x[0]["txn_id"]):
                rw.writerow([a["txn_id"], b["txn_id"], rel])

    for e in w.events:
        if "_row" in e:
            e["disputed_utr"] = e["_row"]["utr"]
    dump(vis / "merchant_events.json", sorted(w.events, key=lambda e: (e["merchant_id"], e.get("date") or e.get("ts") or e.get("period"))))
    dump(vis / "merchants.json", [dict(
        merchant_id=m.mid, business_name=m.business_name, owner_name=m.owner_name.upper(), mcc=m.a["mcc"],
        category=m.a["category"], supply_kind=m.a["kind"], locality=m.locality, city="Bengaluru",
        state="Karnataka", gst_status=m.a["gst"], preferred_language="kn",
        terminals=sorted({r["terminal"] for r in m.rows if r["terminal"]}),
        linked_own_accounts=m.linked_own, data_window=[m.start, m.end],
    ) for m in w.merchants])
    dump(hid / "merchant_truth.json", {m.mid: m.truth for m in w.merchants})
    dump(hid / "fraud_chains.json", w.chains)
    if scenario:
        dump(hid / "demo_scenario.json", scenario)


def write_reference():
    ref_dir = ROOT / "reference"
    ref_dir.mkdir(parents=True, exist_ok=True)
    dump(ref_dir / "hsn_catalog.json", [dict(item=i[0], hsn=i[1], exempt=i[2], basis=C.BASIS[pool])
                                        for pool, items in C.ITEMS.items() for i in items])


def summarize(name, w):
    credits = [r for m in w.merchants for r in m.rows if r["direction"] == "CR"]
    debits = sum(len(m.rows) for m in w.merchants) - len(credits)
    counts = Counter(r["_label"] for r in credits)
    print(f"\n== {name}: {len(credits)} credits, {debits} debits")
    print("   " + "  ".join(f"{lab} {counts[lab] / len(credits):.1%}" for lab in TRUE_LABELS))
    for m in w.merchants:
        t = m.truth
        print(f"   {m.mid:<16} {m.arch_name:<19} d={m.d:.2f}  gross Rs {t['gross_credits'] / 1e5:6.1f}L  "
              f"aggregate Rs {t['aggregate_turnover'] / 1e5:6.1f}L  crosses {t['threshold_crossing_date']}  "
              f"register={t['registration_required']}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=list(SEEDS))
    args = ap.parse_args()
    write_reference()
    for name in [args.only] if args.only else list(SEEDS):
        w, scenario = build_demo() if name == "demo" else build_split(name)
        for m in w.merchants:
            merchant_truth(m)
        write_split(w, name, scenario)
        summarize(name, w)
        if scenario:
            b3, b4 = scenario["beat3_notice"], scenario["beat4_freeze"]
            print(f"   notice claims Rs {b3['claimed_turnover'] / 1e5:.1f}L; true breakdown (L): " + ", ".join(
                f"{k} {v / 1e5:.1f}" for k, v in b3["true_breakdown"].items()))
            print(f"   credits in the 7 days before the freeze: {b4['credits_in_7_days_before_freeze']}")


if __name__ == "__main__":
    main()
