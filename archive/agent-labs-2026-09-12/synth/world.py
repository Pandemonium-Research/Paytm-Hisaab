"""Merchant simulator: the hidden process that produces a visible ledger.

Rows are dicts. Keys without a leading underscore are what Paytm could plausibly show
the system under test; keys with a leading underscore are generator truth and are only
ever written under hidden/. The generator knows nothing about any classifier.
"""
import hashlib
import math
from collections import defaultdict
from datetime import datetime, time, timedelta
from itertools import accumulate

from . import catalog as C

SUPPLY_LABELS = ("taxable_supply", "exempt_supply")
TRUE_LABELS = ("taxable_supply", "exempt_supply", "personal_transfer", "refund_reversal",
               "duplicate", "inter_account", "non_business")  # 'unclassified' is output-only
TERMINAL = {"UPI_QR": "SBX01", "UPI_POS": "POS01", "CARD_POS": "POS01"}
P2P = ("UPI_INTENT", "IMPS", "BANK_TRANSFER")
HOURS = range(24)


def loguniform(rng, lo, hi):
    return math.exp(rng.uniform(math.log(lo), math.log(hi)))


def poisson(rng, lam):
    if lam <= 0:
        return 0
    if lam > 40:
        return max(0, round(rng.gauss(lam, math.sqrt(lam))))
    limit, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= limit:
            return k
        k += 1


def at(d, hour, rng):
    return datetime.combine(d, time(hour, rng.randrange(60), rng.randrange(60)))


def is_sale(r):
    return r["direction"] == "CR" and r["_label"] in SUPPLY_LABELS


def crossing(rows, limit):
    """First date cumulative aggregate turnover (taxable + exempt supplies) exceeds `limit`."""
    total = 0
    for r in sorted((r for r in rows if is_sale(r)), key=lambda r: r["ts"]):
        total += r["_exempt"] + r["_taxable"]
        if total > limit:
            return r["ts"].date()
    return None


class Party:
    """A counterparty. pid/handle/name are visible; role/relation are hidden truth."""

    def __init__(self, pid, handle, name, role, relation=""):
        self.pid, self.handle, self.name, self.role, self.relation = pid, handle, name, role, relation
        self.first = self.surname = ""
        self.card = None


class World:
    """Shared state for one split: rng, id minting, fraud chains, events."""

    def __init__(self, rng, tag):
        self.rng, self.tag = rng, tag
        self._n = 0
        self.merchants, self.chains, self.events = [], [], []

    def party(self, handle, name, role, relation=""):
        self._n += 1
        pid = "P" + hashlib.sha1(f"{self.tag}-{self._n}".encode()).hexdigest()[:10].upper()
        return Party(pid, handle, name, role, relation)

    def person(self, role, relation="", surname=None, gender=None, first=None, handle=None):
        rng = self.rng
        gender = gender or rng.choice("MF")
        first = first or rng.choice(C.MALE if gender == "M" else C.FEMALE)
        surname = surname or rng.choice(C.SURNAMES)
        p = self.party(handle or C.vpa(rng, first, surname), f"{first} {surname}".upper(), role, relation)
        p.first, p.surname = first, surname
        return p

    def business(self, name, role, bank=False):
        if bank:
            handle = C.bank_handle(self.rng)
        else:
            slug = "".join(ch for ch in name.lower() if ch.isalnum())[:14]
            handle = f"{slug}@{self.rng.choice(C.HANDLES)}"
        return self.party(handle, name.upper(), role, name)


class MerchantSim:
    def __init__(self, world, mid, arch_name, difficulty, start, end, owner=None, business=None):
        self.w, self.rng = world, world.rng
        self.mid, self.arch_name, self.a = mid, arch_name, C.ARCHETYPES[arch_name]
        self.d, self.start, self.end = difficulty, start, end
        self.days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
        self.rows, self.rels = [], []
        rng = self.rng
        if owner:
            self.owner_first, self.surname, self.gender = owner
        else:
            self.gender = rng.choice("MF")
            self.owner_first = rng.choice(C.MALE if self.gender == "M" else C.FEMALE)
            self.surname = rng.choice(C.SURNAMES)
        self.owner_name = f"{self.owner_first} {self.surname}"
        self.business_name = business or C.business_name(rng, self.owner_first, self.a)
        self.locality = rng.choice(C.LOCALITIES)
        self.hour_cum = list(accumulate(C.HOURLY[self.a["hours"]]))
        self._make_parties()
        world.merchants.append(self)

    # ---- difficulty -------------------------------------------------------------------
    def cue(self, easy, hard):
        """Probability of a visible cue, interpolated from easy (d=0) to hard (d=1)."""
        return easy + (hard - easy) * self.d

    def _shown(self, p):
        # At higher difficulty UPI shows abbreviated names, which breaks name matching.
        if self.rng.random() < self.cue(0.05, 0.6):
            p.name = (f"{p.first[0]} {p.surname}" if self.rng.random() < 0.5
                      else f"{p.first} {p.surname[0]}").upper()
        return p

    def in_window(self, ts):
        return self.start <= ts.date() <= self.end

    def shop_hour(self):
        return self.rng.choices(HOURS, cum_weights=self.hour_cum)[0]

    # ---- parties ----------------------------------------------------------------------
    def _make_parties(self):
        w, rng, a = self.w, self.rng, self.a
        f, s = self.owner_first, self.surname
        self.own = [
            w.person("own_account", "own savings account", s, first=f,
                     handle=f"{f.lower()}{s.lower()[:3]}{rng.randint(10, 99)}@oksbi"),
            self._shown(w.person("own_account", "own personal UPI", s, first=f,
                                 handle=f"{rng.choice('6789')}{rng.randint(0, 9)}XXXXXX{rng.randint(10, 99)}@ptyes")),
        ]
        # Only accounts the merchant linked in their profile are visible as "own".
        self.linked_own = [self.own[0].handle] + ([self.own[1].handle] if self.d < 0.5 else [])

        spouse_g = "M" if self.gender == "F" else "F"
        spec = [  # relation, gender, transfers/month, round amounts, typical non-round amount
            ("spouse", spouse_g, 2.0, (2000, 3000, 5000, 10000, 15000), 8000),
            ("sibling", None, 0.6, (5000, 10000, 20000, 25000), 12000),
            ("parent", None, 0.7, (2000, 3000, 5000), 4000),
            ("in-law", None, 0.3, (1000, 2000, 5000, 10000), 5000),
        ]
        self.family = []
        for rel, g, rate, rounds, typical in spec:
            same = rel != "in-law" and rng.random() < self.cue(0.95, 0.45)
            p = self._shown(w.person("family", rel, s if same else None, gender=g))
            p.rate, p.rounds, p.typical = rate, rounds, typical
            self.family.append(p)

        n = max(40, int(a["avg_daily"] * 9))
        self.customers = [w.person("customer") for _ in range(n)]
        self.cust_cum = list(accumulate(1 / (i + 1) ** 0.85 for i in range(n)))
        names = rng.sample(C.SUPPLIERS[a["supplier_kind"]], k=min(len(C.SUPPLIERS[a["supplier_kind"]]), rng.randint(2, 4)))
        self.suppliers = [w.business(nm, "supplier") for nm in names]

    def pick_customer(self):
        if self.rng.random() < self.a["walkin_p"]:
            return self.w.person("customer", "walk-in")
        return self.rng.choices(self.customers, cum_weights=self.cust_cum)[0]

    def card_of(self, p):
        if p.card is None:
            p.card = self.w.party(f"XXXX-XXXX-XXXX-{self.rng.randint(1000, 9999)}", "", "customer", p.relation)
        return p.card

    # ---- rows -------------------------------------------------------------------------
    def row(self, ts, direction, channel, party, reason="", label="", note="", orig=None, amount=0):
        r = dict(ts=ts, direction=direction, amount=amount, channel=channel, party=party,
                 terminal=TERMINAL.get(channel, ""), bill=None, note=note, orig=orig,
                 _m=self, _label=label, _reason=reason, _exempt=0, _taxable=0, _cues="",
                 _fraud="", _lines=None, _pinned=False)
        self.rows.append(r)
        return r

    def basket(self, bulk=False):
        rng, a = self.rng, self.a
        ex_pool, tx_pool = a["pools"]
        lines = []
        for _ in range(rng.randint(*a["basket"])):
            pool = ex_pool if ex_pool and (not tx_pool or rng.random() < a["exempt_p"]) else tx_pool
            item = rng.choice(C.ITEMS[pool])
            v = loguniform(rng, item[3], item[4]) * (loguniform(rng, 4, 15) if bulk else 1)
            lines.append([item, v])
        return lines

    def price(self, r, k=1.0):
        """Round raw line values (scaled by k) into the visible amount and hidden split."""
        vals = [max(1, round(v * k)) for _, v in r["_lines"]]
        r["amount"] = sum(vals)
        ex = sum(v for (it, _), v in zip(r["_lines"], vals) if it[2])
        r["_exempt"], r["_taxable"] = ex, r["amount"] - ex
        r["_label"] = "exempt_supply" if ex > r["amount"] - ex else "taxable_supply"
        if r["channel"] in ("UPI_POS", "CARD_POS"):
            r["bill"] = [(it[0], it[1], v) for (it, _), v in zip(r["_lines"], vals)]

    def add_sale(self, ts, payer, lines=None, bulk=None, pinned=False, reason=None, channel=None):
        rng, a = self.rng, self.a
        if bulk is None:
            bulk = rng.random() < a["bulk_p"]
        if channel is None:
            channel = "UPI_QR"
            if rng.random() < a["pos_share"]:
                channel = "CARD_POS" if rng.random() < a["card_share"] else "UPI_POS"
        if channel == "CARD_POS":
            payer = self.card_of(payer)
        reason = reason or ("bulk_order" if bulk else
                            "walkin_purchase" if payer.relation == "walk-in" else "regular_customer_purchase")
        r = self.row(ts, "CR", channel, payer, reason)
        r["_lines"], r["_pinned"] = lines or self.basket(bulk), pinned
        self.price(r)
        r["_cues"] = "pos_bill" if r["bill"] else ""
        return r

    def transfer(self, ts, party, amount, label, reason, channel, note=""):
        r = self.row(ts, "CR", channel, party, reason, label, note, amount=amount)
        cues = []
        if amount % 500 == 0 or amount % 1000 == 1 or amount % 100 == 1:
            cues.append("round_amount")
        if ts.hour >= 21 or ts.hour < 7:
            cues.append("off_hours")
        if channel in P2P:
            cues.append("p2p_channel")
        if self.surname.upper() in party.name:
            cues.append("surname_match")
        if party.handle in self.linked_own:
            cues.append("registered_own_account")
        if note:
            cues.append("note")
        r["_cues"] = "|".join(cues)
        return r

    def drop(self, doomed):
        """Remove rows plus anything that references them (refunds, relationships)."""
        doomed = {id(r) for r in doomed}
        changed = True
        while changed:
            changed = False
            for r in self.rows:
                if id(r) not in doomed and r["orig"] is not None and id(r["orig"]) in doomed:
                    doomed.add(id(r))
                    changed = True
        self.rows = [r for r in self.rows if id(r) not in doomed]
        self.rels = [x for x in self.rels if id(x[0]) not in doomed and id(x[1]) not in doomed]

    # ---- generation -------------------------------------------------------------------
    def gen_sales(self):
        rng, a = self.rng, self.a
        fy_start = self.start.replace(month=4, day=1) if self.start.month >= 4 else self.start.replace(year=self.start.year - 1, month=4, day=1)
        for d in self.days:
            if d not in C.FESTIVALS and rng.random() < 0.012:
                continue  # shop shut for the day
            months = (d - fy_start).days / 30.44
            lam = (a["avg_daily"] * C.DOW[d.weekday()] * C.MONTH[d.month] * C.festival_mult(d)
                   * (1 + a["growth"]) ** months * math.exp(rng.gauss(0, 0.12)))
            for _ in range(poisson(rng, lam)):
                s = self.add_sale(at(d, self.shop_hour(), rng), self.pick_customer())
                if s["channel"] == "UPI_QR" and rng.random() < a["repeat_p"]:
                    # Hard negative: a genuine second purchase that looks like a duplicate.
                    r = self.row(s["ts"] + timedelta(seconds=loguniform(rng, 90, 1200)), "CR", "UPI_QR",
                                 s["party"], "repeat_purchase_same_amount")
                    r["_lines"] = s["_lines"]
                    self.price(r)
                    self.rels.append((r, s, "repeat_of"))

    def calibrate(self, k):
        for r in self.rows:
            if r["_lines"] is not None and not r["_pinned"]:
                self.price(r, k)

    def gen_rest(self):
        self.gen_duplicates()
        self.gen_supply_chain()
        self.gen_personal()
        self.gen_non_business()
        self.drop([r for r in self.rows if not self.in_window(r["ts"])])

    def gen_duplicates(self):
        rng = self.rng
        sales = [r for r in self.rows if r["channel"] == "UPI_QR" and is_sale(r) and not r["_pinned"]]
        for s in sales:
            if rng.random() >= self.a["dup_p"]:
                continue
            gap = loguniform(rng, 15, self.cue(120, 1800))
            dup = self.row(s["ts"] + timedelta(seconds=gap), "CR", "UPI_QR", s["party"],
                           "customer_retry_double_payment", "duplicate", amount=s["amount"])
            cues = [f"gap_{int(gap)}s"]
            delay = timedelta(minutes=loguniform(rng, 3, self.cue(90, 4320)))
            if rng.random() < self.cue(0.95, 0.6) and self.in_window(dup["ts"] + delay):
                target = dup
                if rng.random() < self.cue(0.1, 0.35):  # merchant refunded the first payment instead
                    target = s
                    for k in ("_label", "_reason", "_exempt", "_taxable", "_lines"):
                        s[k], dup[k] = dup[k], s[k]
                note = "double payment refund" if rng.random() < self.cue(0.5, 0.1) else ""
                ref = self.row(target["ts"] + delay, "DR", "REFUND", s["party"], note=note,
                               orig=target, amount=s["amount"])
                self.rels.append((ref, target, "refund_of"))
                cues.append("refund_linked")
            dupe, sale = (s, dup) if s["_label"] == "duplicate" else (dup, s)
            dupe["_cues"] = "|".join(cues)
            self.rels.append((dupe, sale, "duplicate_of"))

    def gen_supply_chain(self):
        """Supplier payments (DR), own-account top-ups before them, vendor refunds, reversals, sweeps."""
        rng, a = self.rng, self.a
        daily = defaultdict(int)
        for r in self.rows:
            if is_sale(r):
                daily[r["ts"].date()] += r["amount"]
        acc = 0
        for d in self.days:
            acc += daily[d]
            if d.weekday() == 6 and rng.random() < a["sweep_p"]:
                week = sum(daily[d - timedelta(days=i)] for i in range(7))
                if week:
                    self.row(at(d, rng.choice((21, 22)), rng), "DR", "UPI_OUT", self.own[0],
                             amount=max(1000, int(round(week * rng.uniform(0.25, 0.5), -3))))
            if acc == 0 or rng.random() >= a["supplier_days"] / 7:
                continue
            pay = self.row(at(d, rng.choice(a["supplier_hours"]), rng), "DR", "UPI_OUT",
                           rng.choice(self.suppliers), note=rng.choice(("", "", "stock", "bill")),
                           amount=int(round(acc * rng.uniform(0.62, 0.82), -1)))
            acc = 0
            if rng.random() < a["own_topup"]:
                self._topup(pay)
            u = rng.random()
            if u < 0.035:
                self._vendor_refund(pay)
            elif u < 0.042:
                self._reversal(pay)
        # A few standalone top-ups at the start of the month.
        for d in self.days:
            if d.day == rng.randint(1, 5) and rng.random() < min(1, a["own_topup"] * 1.2):
                self.transfer(at(d, rng.choice((8, 9, 20, 21)), rng), self.own[rng.random() < 0.3],
                              rng.choice((5000, 10000, 15000, 20000, 25000)), "inter_account",
                              "own_account_month_start_topup", rng.choice(("UPI_INTENT", "IMPS")))

    def _topup(self, pay):
        rng = self.rng
        unit = 5000 if rng.random() < 0.6 else 1000
        amt = max(unit, math.ceil(pay["amount"] * rng.uniform(0.35, 1.0) / unit) * unit)
        ts = pay["ts"] - timedelta(minutes=loguniform(rng, 4, 150))
        r = self.transfer(ts, self.own[rng.random() < 0.35], amt, "inter_account",
                          "own_account_topup_before_supplier_payment",
                          "UPI_INTENT" if rng.random() < 0.75 else "IMPS")
        self.rels.append((r, pay, "funds_for"))

    def _vendor_refund(self, pay):
        rng = self.rng
        amt = int(round(pay["amount"] * rng.uniform(0.05, 0.3), -2 if rng.random() < 0.5 else -1))
        ts = pay["ts"] + timedelta(hours=loguniform(rng, 1, 72))
        note = rng.choice(("short supply", "crate return", "rate difference", "damaged stock return")) \
            if rng.random() < self.cue(0.6, 0.15) else ""
        r = self.transfer(ts, pay["party"], max(amt, 10), "refund_reversal", "supplier_short_supply_refund",
                          "UPI_INTENT", note)
        self.rels.append((r, pay, "vendor_refund_for"))

    def _reversal(self, pay):
        ts = pay["ts"] + timedelta(minutes=loguniform(self.rng, 1, 30))
        r = self.row(ts, "CR", "UPI_REVERSAL", pay["party"], "failed_payout_reversal", "refund_reversal",
                     "REVERSAL", orig=pay, amount=pay["amount"])
        r["_cues"] = "orig_linked"
        self.rels.append((r, pay, "reversal_of"))

    def gen_personal(self):
        rng = self.rng
        for p in self.family:
            rate = p.rate * self.a["family"] / 30.44
            for d in self.days:
                if rng.random() >= rate:
                    continue
                if rng.random() < self.cue(0.85, 0.3):
                    amt = rng.choice(p.rounds)
                else:
                    amt = int(round(p.typical * loguniform(rng, 0.35, 1.5), -1))
                hour = rng.choice((6, 21, 22, 23)) if rng.random() < self.cue(0.75, 0.3) else self.shop_hour()
                ch = "UPI_INTENT" if rng.random() < self.cue(0.9, 0.4) else "UPI_QR"
                note = rng.choice(C.PERSONAL_NOTES) if rng.random() < self.cue(0.45, 0.08) else ""
                self.transfer(at(d, hour, rng), p, amt, "personal_transfer",
                              f"{p.relation.replace('-', '')}_household_transfer", ch, note)

    def gen_non_business(self):
        rng, w, nb = self.rng, self.w, self.a["nonbiz"]
        weekdays = [d for d in self.days if d.weekday() < 5]

        def bank_ts():
            return at(rng.choice(weekdays), rng.randint(10, 16), rng)

        def maybe(note, easy, hard):
            return note if rng.random() < self.cue(easy, hard) else ""

        if rng.random() < 0.5 * nb:
            lender = w.business(rng.choice(C.LENDERS), "lender", bank=True)
            self.transfer(bank_ts(), lender, rng.choice((100000, 150000, 200000, 300000)), "non_business",
                          "loan_disbursal", "BANK_TRANSFER", maybe(f"LOAN DISB {rng.randint(10**7, 10**8 - 1)}", 0.9, 0.4))
        if rng.random() < 0.6 * nb:
            if rng.random() < self.cue(0.9, 0.5):
                chit, ch = w.business(rng.choice(C.CHITS), "chit_fund", bank=True), "BANK_TRANSFER"
            else:
                chit, ch = w.person("chit_fund", "chit organiser"), "UPI_INTENT"
            for _ in range(rng.randint(1, 2)):
                value = rng.choice((50000, 100000, 150000, 200000))
                self.transfer(bank_ts(), chit, value - rng.randrange(0, int(value * 0.3), 500), "non_business",
                              "chit_fund_payout", ch, maybe("chit", 0.6, 0.15))
        for fest in C.GIFT_FESTIVALS:
            if not self.start <= fest <= self.end:
                continue
            for _ in range(poisson(rng, 0.8 * nb)):
                giver = w.person("gift_giver", "friend / extended family")
                amt = (rng.choice((501, 1001, 1101, 2001, 2100, 5001)) if rng.random() < self.cue(0.8, 0.35)
                       else rng.choice((1000, 2000, 3000, 5000)))
                d = fest - timedelta(days=rng.randint(0, 2))
                self.transfer(at(d, rng.randint(7, 22), rng), giver, amt, "non_business", "festival_gift",
                              "UPI_INTENT", maybe(rng.choice(C.GIFT_NOTES), 0.5, 0.1))
        if rng.random() < 0.5 * nb:
            friend = w.person("friend", "friend")
            for _ in range(rng.randint(1, 3)):
                self.transfer(at(rng.choice(self.days), self.shop_hour(), rng), friend,
                              rng.choice((3000, 5000, 10000, 20000)), "non_business", "hand_loan_repaid",
                              "UPI_INTENT", maybe(rng.choice(("returning loan", "hand loan", "thanks")), 0.5, 0.1))
        if rng.random() < 0.25 * nb:
            landlord = w.person("landlord", "former landlord")
            self.transfer(bank_ts(), landlord, rng.choice((25000, 50000, 75000, 100000)), "non_business",
                          "rent_deposit_returned", rng.choice(("UPI_INTENT", "IMPS")), maybe("advance return", 0.7, 0.2))
        if rng.random() < 0.15 * nb:
            ins = w.business(rng.choice(C.INSURERS), "insurer", bank=True)
            self.transfer(bank_ts(), ins, rng.randrange(8000, 60000, 10) + rng.randint(1, 9), "non_business",
                          "insurance_claim", "BANK_TRANSFER", maybe("CLAIM SETTLEMENT", 0.9, 0.4))

    # ---- seeded scenario rows ---------------------------------------------------------
    def exact_sale(self, ts, payer, amount, channel, reason="bulk_order"):
        """A pinned bulk sale of exactly `amount`; pinned rows are exempt from calibration."""
        lines = self.basket(bulk=True)
        k = amount / sum(v for _, v in lines)
        s = self.add_sale(ts, payer, lines=[[it, v * k] for it, v in lines], pinned=True,
                          reason=reason, channel=channel)
        s["_lines"][0][1] += amount - s["amount"]
        self.price(s)
        return s

    def inject_fraud(self, ts, amount, chain_id, freeze_ts, lea):
        """A genuine sale paid by a layer-2 mule, three hops downstream of a victim."""
        rng, w = self.rng, self.w
        victim = w.person("victim", "fraud victim")
        mule_a = w.person("fraud_mule", "layer-1 mule")
        mule_b = w.person("fraud_mule", "layer-2 mule")
        s = self.exact_sale(ts, mule_b, amount, "UPI_POS" if self.a["pos_share"] else "UPI_QR",
                            "purchase_by_fraud_layer_payer")
        s["_fraud"] = chain_id
        t1 = ts - timedelta(days=2, hours=rng.randint(1, 6))
        t2 = ts - timedelta(hours=rng.randint(20, 30))
        hop = lambda a, b, amt, t, layer: dict(layer=layer, from_name=a.name, from_handle=a.handle,
                                               to_name=b.name, to_handle=b.handle, amount=amt,
                                               ts=t.isoformat() + "+05:30")
        others = [w.person("fraud_mule", "sibling mule") for _ in range(2)]
        chain = dict(
            chain_id=chain_id, scheme="part-time job / task scam", merchant_id=self.mid,
            victim=dict(name=victim.name, city=lea["city"], state=lea["state"]),
            hops=[hop(victim, mule_a, 50000, t1, 1),
                  hop(mule_a, mule_b, 20000, t2, 2),
                  hop(mule_a, others[0], 15000, t2 + timedelta(minutes=7), 2),
                  hop(mule_a, others[1], 12000, t2 + timedelta(minutes=19), 2),
                  hop(mule_b, Party("", self.mid, self.business_name.upper(), "merchant"), amount, ts, 3)],
            merchant_credit=s,
            note="The merchant credit is a genuine sale; provenance label and fraud linkage are independent.",
        )
        w.chains.append(chain)
        w.events.append(dict(
            type="account_frozen", merchant_id=self.mid, ts=freeze_ts.isoformat() + "+05:30",
            freeze_type="debit_freeze", scope="entire account",
            intimation="Bank intimation: account debit-frozen on instruction of law enforcement "
                       "under NCRP complaint. Contact the investigating officer.",
            lea=dict(unit=f"Cyber Crime Police Station, {lea['city']}", state=lea["state"],
                     ncrp_ack=lea["ncrp_ack"], case_ref=lea["case_ref"]),
            disputed_amount=amount, disputed_date=ts.date().isoformat(), _row=s,
        ))
        return s, chain
