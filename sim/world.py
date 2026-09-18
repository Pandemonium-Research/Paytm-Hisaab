"""The process that plays out a year in one shop.

The generator decides what really happened first (this payment is the spouse sending household
money), then records only what Paytm would see. `World.build()` runs the whole year for one
merchant; generate.py assigns IDs across a split and writes files.

Order matters, and is fixed in `build()`:
  people -> sales -> repeat purchases -> fraud chains -> scenario pins and calibration
  -> duplicates -> family, non-business, own top-ups -> scenario pins -> ledger pass
  (supplier payments, top-ups, refunds, reversals, sweeps, balances, declines)
  -> tax events -> merchant answer sheet -> cues
"""

from __future__ import annotations

import hashlib
import heapq
import itertools
import math
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone

from . import catalog as C

IST = timezone(timedelta(hours=5, minutes=30))
P2P_CHANNELS = ("UPI_INTENT", "IMPS", "BANK_TRANSFER")


def at(d: date, hour: int, minute: int = 0, second: int = 0) -> datetime:
    return datetime(d.year, d.month, d.day, hour, minute, second, tzinfo=IST)


def poisson(rng: random.Random, lam: float) -> int:
    if lam <= 0:
        return 0
    if lam < 30:
        limit, k, p = math.exp(-lam), 0, 1.0
        while True:
            p *= rng.random()
            if p <= limit:
                return k
            k += 1
    return max(0, int(round(rng.gauss(lam, math.sqrt(lam)))))


def days(start: date, end: date):
    d = start
    while d <= end:
        yield d
        d += timedelta(days=1)


# ---------------------------------------------------------------- records


@dataclass(eq=False)
class Party:
    name: str            # as UPI displays it
    handle: str          # VPA, masked account or masked card
    role: str            # customer, family, own, supplier, friend, lender, chit, insurer, landlord, mule
    relation: str = ""   # regular / walk_in / spouse / savings / personal_upi / ...
    linked: bool = False  # own account linked in the merchant's Paytm profile
    card: str = ""
    pid: str = ""

    def __post_init__(self):
        if not self.pid:
            digest = hashlib.sha1(f"{self.role}|{self.name}|{self.handle}".encode()).hexdigest()
            self.pid = "P" + digest[:10].upper()


@dataclass(eq=False)
class Line:
    item: str
    hsn: str
    exempt: bool
    qty: float
    unit: str
    amount: int


@dataclass(eq=False)
class Txn:
    merchant_id: str
    ts: datetime
    direction: str                  # CR / DR
    amount: int
    channel: str
    party: Party
    terminal: str = ""
    lines: list[Line] | None = None  # basket; visible only when billed
    billed: bool = False
    note: str = ""
    orig: Txn | None = None
    label: str = ""                 # hidden truth (credits only)
    reason: str = ""
    cues: list[str] = field(default_factory=list)
    fraud_chain_id: str = ""
    tags: set[str] = field(default_factory=set)
    pinned: bool = False            # placed by a scenario
    locked: bool = False            # never scaled, removed or re-timed
    txn_id: str = ""
    utr: str = ""

    @property
    def is_supply(self) -> bool:
        return self.label in C.SUPPLY_LABELS

    @property
    def exempt_value(self) -> int:
        if not self.is_supply or not self.lines:
            return 0
        return sum(line.amount for line in self.lines if line.exempt)

    @property
    def taxable_value(self) -> int:
        return self.amount - self.exempt_value if self.is_supply else 0


@dataclass
class MerchantSpec:
    merchant_id: str
    archetype: str
    difficulty: float
    region: str
    seed: int
    window: tuple[date, date] = (C.FY_START, C.FY_END)
    business_name: str | None = None
    owner: tuple[str, str] | None = None
    place_index: int = 0
    fraud_freeze: bool = False
    lea_inquiry: bool = False
    tax_notice: bool = False
    notice: dict = field(default_factory=dict)
    onboarded_on: date | None = None
    target_turnover: int | None = None  # scale sales so FY aggregate turnover lands here


class Scenario:
    """Hooks a demo scenario uses to pin and calibrate. The default does nothing."""

    name = "none"

    def setup(self, w: World): ...
    def after_sales(self, w: World): ...
    def after_money(self, w: World): ...

    def ledger_pass(self, w: World):
        w.run_pass()

    def check(self, w: World): ...

    def describe(self, w: World, ref) -> dict | None:
        return None


# ---------------------------------------------------------------- the world


class World:
    def __init__(self, spec: MerchantSpec, scenario: Scenario | None = None):
        self.spec = spec
        self.merchant_id = spec.merchant_id
        self.cfg = C.ARCHETYPES[spec.archetype]
        self.d = spec.difficulty
        self.rng = random.Random(spec.seed)
        self.region = C.REGIONS[spec.region]
        self.scenario = scenario or Scenario()
        self.start, self.end = spec.window

        self.pre: list[Txn] = []            # created before the ledger pass
        self.txns: list[Txn] = []           # final, after the pass
        self.rel_pre: list[tuple[Txn, Txn, str]] = []
        self.relationships: list[tuple[Txn, Txn, str]] = []
        self.events_pre: list[dict] = []
        self.events: list[dict] = []
        self.fraud_chains: list[dict] = []
        self.freeze_ts: datetime | None = None
        self.balances: list[dict] = []
        self.quiet_dates: set[date] = set()    # no unpinned non-sale credits, no P2P sales
        self.no_dup_dates: set[date] = set()
        self.forced_supplier_times: list[datetime] = []
        self.notice: dict | None = None
        self.returns: list[dict] = []
        self.answers: dict[Txn, dict] = {}
        self.behaviour: dict = {}

    # ------------------------------------------------------------ helpers

    def cue(self, easy: float, hard: float) -> float:
        return easy + (hard - easy) * self.d

    def _name(self, region: dict | None = None) -> tuple[str, str]:
        rng = self.rng
        if region is None:
            region = self.region if rng.random() < 0.8 else rng.choice(list(C.REGIONS.values()))
        return rng.choice(region["first"]), rng.choice(region["surnames"])

    def _display(self, first: str, surname: str, p_abbrev: float, p_middle: float = 0.0) -> str:
        if self.rng.random() < p_abbrev:
            return self.rng.choice([f"{first[0]} {surname}", f"{first} {surname[0]}"]).upper()
        if self.rng.random() < p_middle:
            return f"{first} {self.rng.choice('ABCDGHJKLMNPRSTV')} {surname}".upper()
        return f"{first} {surname}".upper()

    def _handle(self, first: str, surname: str) -> str:
        rng, psp = self.rng, self.rng.choice(C.PSP_SUFFIXES)
        style = rng.random()
        if style < 0.45:
            return f"{first.lower()}.{surname.lower()}{rng.randint(1, 99)}@{psp}"
        if style < 0.75:
            return f"{first.lower()}{surname[:3].lower()}{rng.randint(10, 99)}@{psp}"
        return f"{rng.choice('6789')}{rng.randint(0, 9)}XXXXXX{rng.randint(10, 99)}@{psp}"

    def _account(self) -> str:
        return f"XXXXXXXX{self.rng.randint(1000, 9999)}"

    def _person(self, role: str, relation: str, region: dict | None = None,
                p_abbrev: float = 0.15) -> Party:
        first, surname = self._name(region)
        owner = getattr(self, "owner_name", "")
        for _ in range(10):  # a stranger with exactly the owner's name is rare in real life
            name = self._display(first, surname, p_abbrev, p_middle=0.3)
            if name != owner and not (owner and name.split()[-1] == owner.split()[-1]
                                      and name.split()[0] == owner.split()[0]):
                break
            first, surname = self._name(region)
        return Party(name, self._handle(first, surname), role, relation)

    def _random_day(self, lo: date, hi: date, avoid: set[date] | None = None) -> date:
        avoid = avoid or set()
        span = (hi - lo).days
        for _ in range(20):
            d = lo + timedelta(days=self.rng.randint(0, max(0, span)))
            if d not in avoid:
                return d
        return lo

    # ------------------------------------------------------------ people

    def setup_people(self):
        rng, reg, cfg = self.rng, self.region, self.cfg
        first, surname = self.spec.owner or (rng.choice(reg["first"]), rng.choice(reg["surnames"]))
        self.owner_first, self.owner_surname = first, surname
        self.owner_name = f"{first} {surname}".upper()
        city, locality, pincode, lat, lon = reg["places"][self.spec.place_index % len(reg["places"])]
        self.place = dict(city=city, locality=locality, pincode=pincode, state=reg["state"],
                          lat=lat, lon=lon)
        self.business_name = self.spec.business_name or self._business_name()
        self.settlement_account = self._account()
        self.onboarded_on = self.spec.onboarded_on or date(
            rng.randint(2021, 2024), rng.randint(1, 12), rng.randint(1, 28))

        psp = rng.choice(["oksbi", "okhdfcbank", "okicici", "okaxis"])
        self.own = {
            "savings": Party(self.owner_name,
                             f"{first.lower()}{surname[:3].lower()}{rng.randint(10, 99)}@{psp}",
                             "own", "savings", linked=True),
            "personal_upi": Party(self._display(first, surname, self.cue(0.05, 0.6)),
                                  f"{rng.choice('6789')}{rng.randint(0, 9)}XXXXXX"
                                  f"{rng.randint(10, 99)}@{rng.choice(C.PSP_SUFFIXES)}",
                                  "own", "personal_upi", linked=self.d < 0.5),
        }

        self.family: dict[str, Party] = {}
        for rel in ("spouse", "sibling", "parent", "in_law"):
            f_first = rng.choice([n for n in reg["first"] if n != first])
            if rng.random() < self.cue(0.95, 0.45):
                f_surname = surname
            else:
                f_surname = rng.choice([s for s in reg["surnames"] if s != surname])
            self.family[rel] = Party(self._display(f_first, f_surname, self.cue(0.05, 0.6)),
                                     self._handle(f_first, f_surname), "family", rel)

        templates = C.SUPPLIER_TEMPLATES[cfg["supplier_kind"]]
        names: list[str] = []
        for _ in range(rng.randint(*cfg["suppliers"])):
            for _ in range(10):
                name = rng.choice(templates).format(
                    deity=rng.choice(C.DEITIES), place=locality.upper(),
                    surname=rng.choice(reg["surnames"]).upper())
                if name not in names:
                    names.append(name)
                    break
        self.suppliers = []
        for name in names:
            slug = "".join(ch for ch in name.lower() if ch.isalpha())[:14]
            handle = (f"{slug}{rng.randint(1, 99)}@okaxis" if rng.random() < 0.6
                      else self._account())
            self.suppliers.append(Party(name, handle, "supplier", "supplier"))

        self.regulars = [self._person("customer", "regular", p_abbrev=0.2)
                         for _ in range(cfg["regulars"])]
        weights = [1.0 / (i + 1) ** 0.9 for i in range(len(self.regulars))]
        self.regular_cum = list(itertools.accumulate(weights))
        self.friends = [self._person("friend", "friend", p_abbrev=0.25) for _ in range(8)]
        self.lender = Party(rng.choice(C.LENDERS), self._account(), "lender", "loan")
        self.chit = Party(rng.choice(C.CHIT_FUNDS), self._account(), "chit", "chit")
        self.insurer = Party(rng.choice(C.INSURERS), self._account(), "insurer", "insurance")
        self.landlord = self._person("landlord", "landlord", p_abbrev=0.1)

        self.terminals = [dict(terminal_id="SBX01", kind="soundbox")]
        if cfg["pos_share"] > 0:
            self.terminals.append(dict(terminal_id="POS01", kind="pos"))

    def _business_name(self) -> str:
        rng, kind = self.rng, self.spec.archetype
        first, surname = self.owner_first, self.owner_surname
        deity = rng.choice(C.DEITIES).title()
        options = {
            "veg_vendor": [f"{first} Vegetables", f"Sri {deity} Fruits & Vegetables"],
            "mixed_kirana": [f"{surname} General Stores", f"{deity} Provision Stores"],
            "family_kirana": [f"{first} Stores", f"Sri {deity} Kirana"],
            "mobile_accessories": [f"{first} Mobile Point", f"{surname} Mobile Accessories"],
            "darshini": [f"Sri {deity} Darshini", f"{self.place['locality']} Tiffin Centre"],
            "composition_kirana": [f"{surname} Super Market", f"{deity} Mart"],
        }.get(kind, [f"{first} Stores"])
        return rng.choice(options)

    # ------------------------------------------------------------ sales

    def _volume(self, d: date) -> float:
        cfg = self.cfg
        months = (d.year - self.start.year) * 12 + d.month - self.start.month + d.day / 30.0
        base = cfg["avg_daily"] * C.DOW_FACTOR[d.weekday()] * (1 + cfg["growth"]) ** months
        bump = 1.0
        for offset, weight in ((0, 1.0), (-1, 0.5), (1, 0.5), (-2, 0.25)):
            fest = C.FESTIVALS.get(d + timedelta(days=-offset))
            if fest:
                bump = max(bump, 1 + (fest[1] - 1) * weight)
        return base * bump * max(0.5, self.rng.gauss(1.0, 0.08))

    def _customer(self) -> Party:
        rng = self.rng
        if rng.random() < self.cfg["regular_share"]:
            return rng.choices(self.regulars, cum_weights=self.regular_cum)[0]
        return self._person("customer", "walk_in")

    def _group_items(self, exempt: bool) -> list[tuple]:
        cfg, rng = self.cfg, self.rng
        groups = cfg["exempt_groups"] if exempt else cfg["taxable_groups"]
        group = rng.choices(list(groups), weights=list(groups.values()))[0]
        return [row for row in C.ITEMS if row[4] == group]

    def _line(self, exempt: bool, bulk: bool = False) -> Line:
        rng = self.rng
        name, hsn, is_exempt, _basis, _group, unit, (lo, hi), qtys = rng.choice(
            self._group_items(exempt))
        qty = rng.choice(qtys) * (rng.randint(4, 15) if bulk else 1)
        return Line(name, hsn, is_exempt, qty, unit, max(1, round(qty * rng.randint(lo, hi))))

    def _basket(self, bulk: bool = False) -> list[Line]:
        rng, cfg = self.rng, self.cfg
        lines: dict[str, Line] = {}
        for _ in range(rng.randint(*cfg["basket"])):
            line = self._line(rng.random() < cfg["exempt_share"], bulk)
            if line.item in lines:
                lines[line.item].qty += line.qty
                lines[line.item].amount += line.amount
            else:
                lines[line.item] = line
        return list(lines.values())

    def basket_for_amount(self, amount: int) -> list[Line]:
        """A plausible basket whose lines add up to exactly `amount`."""
        rng, cfg = self.rng, self.cfg
        lines: list[Line] = []
        while sum(line.amount for line in lines) < amount * 0.7:
            lines.append(self._line(rng.random() < cfg["exempt_share"], bulk=amount > 2000))
        while lines and sum(line.amount for line in lines) >= amount:
            lines.pop()
        remainder = amount - sum(line.amount for line in lines)
        name, hsn, is_exempt, _b, _g, unit, (lo, hi), _qtys = rng.choice(
            self._group_items(rng.random() < cfg["exempt_share"]))
        mid = (lo + hi) / 2
        if unit in ("kg", "litre", "dozen"):
            qty = max(0.25, round(remainder / mid * 4) / 4)
        else:
            qty = max(1, round(remainder / mid))
        final = Line(name, hsn, is_exempt, qty, unit, remainder)
        for line in lines:
            if line.item == final.item:
                line.qty += final.qty
                line.amount += final.amount
                break
        else:
            lines.append(final)
        return lines

    def label_sale(self, t: Txn):
        exempt = sum(line.amount for line in t.lines if line.exempt)
        t.amount = sum(line.amount for line in t.lines)
        t.label = "exempt_supply" if exempt * 2 > t.amount else "taxable_supply"
        side = "exempt" if t.label == "exempt_supply" else "taxable"
        t.reason = t.reason or f"sale of {len(t.lines)} item(s); {side} goods hold most of the value"
        if self.cfg["supply_kind"] == "services":
            t.reason = f"restaurant sale of {len(t.lines)} item(s)"

    def make_sale(self, ts: datetime, party: Party | None = None, lines: list[Line] | None = None,
                  channel: str | None = None, bulk: bool | None = None) -> Txn:
        rng, cfg = self.rng, self.cfg
        party = party or self._customer()
        if bulk is None:
            bulk = rng.random() < cfg["bulk_p"]
        lines = lines or self._basket(bulk)
        if channel is None:
            r = rng.random()
            if r < cfg["pos_share"]:
                channel = "CARD_POS" if rng.random() < cfg["card_share"] else "UPI_POS"
            elif r < cfg["pos_share"] + cfg["p2p_sale_share"]:
                channel = "UPI_INTENT"
            else:
                channel = "UPI_QR"
        billed = channel in ("UPI_POS", "CARD_POS")
        terminal = "POS01" if billed else ("SBX01" if channel == "UPI_QR" else "")
        if channel == "CARD_POS" and not party.card:
            party.card = f"XXXX-XXXX-XXXX-{rng.randint(1000, 9999)}"
        t = Txn(self.merchant_id, ts, "CR", 0, channel, party, terminal, lines, billed,
                tags={"sale"})
        self.label_sale(t)
        return t

    def gen_sales(self):
        rng, curve = self.rng, C.HOUR_CURVES[self.cfg["hour_curve"]]
        for d in days(self.start, self.end):
            if rng.random() < self.cfg["closed_p"]:
                continue
            for _ in range(poisson(rng, self._volume(d))):
                hour = rng.choices(range(24), weights=curve)[0]
                ts = at(d, hour, rng.randint(0, 59), rng.randint(0, 59))
                sale = self.make_sale(ts)
                if d in self.quiet_dates and sale.channel == "UPI_INTENT":
                    sale.channel, sale.terminal = "UPI_QR", "SBX01"
                self.pre.append(sale)

    def gen_repeats(self):
        """Hard negatives: a customer genuinely buys the same thing again minutes later."""
        rng = self.rng
        for t in [t for t in self.pre if "sale" in t.tags and t.channel == "UPI_QR"]:
            if t.ts.date() in self.quiet_dates or rng.random() >= self.cfg["repeat_rate"]:
                continue
            gap = rng.randint(300, 1200)
            ts = t.ts + timedelta(seconds=gap)
            if ts.date() != t.ts.date():
                continue
            lines = [Line(x.item, x.hsn, x.exempt, x.qty, x.unit, x.amount) for x in t.lines]
            again = Txn(self.merchant_id, ts, "CR", t.amount, "UPI_QR", t.party, "SBX01", lines,
                        tags={"sale", "repeat"}, cues=[f"gap_{gap}s"])
            self.label_sale(again)
            again.reason = "genuine repeat purchase of the same basket"
            self.pre.append(again)
            self.rel_pre.append((again, t, "repeat_of"))

    # ------------------------------------------------------------ calibration

    def free_sales(self) -> list[Txn]:
        return [t for t in self.pre if "sale" in t.tags and not t.locked]

    def scale_free_sales(self, k: float):
        for t in self.free_sales():
            for line in t.lines:
                line.amount = max(1, round(line.amount * k))
            self.label_sale(t)

    def calibrate_crossing(self, target: date, threshold: int) -> float:
        """Scale unlocked sales so aggregate turnover first goes above `threshold` on `target`."""
        sales = sorted((t for t in self.pre if t.is_supply), key=lambda t: t.ts)

        def crossing(k: float) -> date | None:
            cum = 0
            for t in sales:
                cum += t.amount if t.locked else sum(max(1, round(x.amount * k)) for x in t.lines)
                if cum > threshold:
                    return t.ts.date()
            return None

        def through(day: date) -> tuple[int, int]:
            locked = sum(t.amount for t in sales if t.locked and t.ts.date() <= day)
            free = sum(t.amount for t in sales if not t.locked and t.ts.date() <= day)
            return locked, free

        l_prev, f_prev = through(target - timedelta(days=1))
        l_day, f_day = through(target)
        k = (threshold - (l_prev + l_day) / 2) / ((f_prev + f_day) / 2)
        if crossing(k) != target:
            lo, hi = 0.05, 20.0
            for _ in range(80):
                k = (lo + hi) / 2
                c = crossing(k)
                if c == target:
                    break
                if c is None or c > target:
                    lo = k
                else:
                    hi = k
        if crossing(k) != target:
            raise AssertionError(f"{self.merchant_id}: cannot calibrate crossing to {target}")
        self.scale_free_sales(k)
        return k

    def calibrate_total(self, target_total: int) -> float:
        sales = [t for t in self.pre if t.is_supply]
        locked = sum(t.amount for t in sales if t.locked)
        free = sum(t.amount for t in sales if not t.locked)
        k = (target_total - locked) / free
        self.scale_free_sales(k)
        return k

    # ------------------------------------------------------------ duplicates

    def gen_duplicates(self):
        rng = self.rng
        candidates = [t for t in self.pre if "sale" in t.tags and t.channel == "UPI_QR"
                      and not t.locked and "repeat" not in t.tags]
        linked = {id(a) for a, b, _ in self.rel_pre} | {id(b) for a, b, _ in self.rel_pre}
        for t in candidates:
            day = t.ts.date()
            if (id(t) in linked or day in self.quiet_dates or day in self.no_dup_dates
                    or rng.random() >= self.cfg["dup_rate"]):
                continue
            gap = rng.randint(4, int(self.cue(120, 1800)))
            twin_ts = t.ts + timedelta(seconds=gap)
            lines = [Line(x.item, x.hsn, x.exempt, x.qty, x.unit, x.amount) for x in t.lines]
            twin = Txn(self.merchant_id, twin_ts, "CR", t.amount, "UPI_QR", t.party, "SBX01",
                       lines, tags={"sale"})
            self.label_sale(twin)
            refund = None
            refunded = None
            if rng.random() < self.cue(0.95, 0.6):
                refunded = t if rng.random() < self.cue(0.10, 0.35) else twin
                refund_ts = twin_ts + timedelta(seconds=rng.randint(600, 26 * 3600))
                while refund_ts.date() in self.quiet_dates:
                    refund_ts = at(refund_ts.date() + timedelta(days=1), 10, rng.randint(0, 59))
                if refund_ts.date() > self.end or (self.freeze_ts and refund_ts >= self.freeze_ts):
                    refunded = None
                else:
                    refund = Txn(self.merchant_id, refund_ts, "DR", t.amount, "REFUND", t.party,
                                 orig=refunded, tags={"customer_refund"},
                                 note=rng.choice(["", "", "double payment refund"]))
            dup = refunded or twin
            kept = t if dup is twin else twin
            dup.tags = {"duplicate"}
            dup.label = "duplicate"
            dup.reason = ("paid twice; this twin was refunded" if refunded
                          else "paid twice; later twin, never refunded")
            dup.cues.append(f"gap_{gap}s")
            kept.cues.append(f"gap_{gap}s")
            if refunded:
                dup.cues.append("refund_linked")
            self.pre.append(twin)
            self.rel_pre.append((dup, kept, "duplicate_of"))
            if refund:
                self.pre.append(refund)
                self.rel_pre.append((refund, refunded, "refund_of"))

    # ------------------------------------------------------------ other money in

    def _credit(self, ts: datetime, amount: int, channel: str, party: Party, label: str,
                reason: str, note: str = "", tags: set[str] | None = None) -> Txn:
        terminal = "SBX01" if channel == "UPI_QR" else ""
        t = Txn(self.merchant_id, ts, "CR", int(amount), channel, party, terminal, note=note,
                label=label, reason=reason, tags=tags or {label})
        self.pre.append(t)
        return t

    def _off_hours_ts(self, d: date, off_hours: bool) -> datetime:
        rng = self.rng
        hour = rng.choice([21, 22, 23, 6]) if off_hours else rng.randint(10, 19)
        return at(d, hour, rng.randint(0, 59), rng.randint(0, 59))

    def gen_family(self):
        rng, cfg = self.rng, self.cfg
        rates = {"spouse": 2.0, "sibling": 0.5, "parent": 0.4, "in_law": 0.3}
        month = date(self.start.year, self.start.month, 1)
        while month <= self.end:
            nxt = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
            lo, hi = max(month, self.start), min(nxt - timedelta(days=1), self.end)
            for rel, rate in rates.items():
                party = self.family[rel]
                for _ in range(min(6, poisson(rng, rate * cfg["family"]))):
                    d = self._random_day(lo, hi, self.quiet_dates)
                    if d in self.quiet_dates:
                        continue
                    if rng.random() < self.cue(0.85, 0.3):
                        amount = rng.choice([500, 1000, 1000, 1500, 2000, 2500, 3000, 5000, 5000,
                                             7500, 10000])
                    else:
                        amount = rng.randint(25, 900) * 10 - rng.choice([30, 70, 150, 190])
                        if amount % 500 == 0:
                            amount += 20
                    channel = "UPI_INTENT" if rng.random() < self.cue(0.9, 0.4) else "UPI_QR"
                    note = (rng.choice(self.region["family_notes"])
                            if rng.random() < self.cue(0.45, 0.08) else "")
                    ts = self._off_hours_ts(d, rng.random() < self.cue(0.75, 0.3))
                    self._credit(ts, amount, channel, party, "personal_transfer",
                                 f"household money from the owner's {rel.replace('_', '-')}", note)
            month = nxt

    def gen_nonbusiness(self):
        rng, nb = self.rng, self.cfg["nonbiz"]
        quiet = self.quiet_dates
        lo, hi = self.start, self.end

        if rng.random() < 0.35 * nb:
            amount = rng.choice([100, 150, 200, 250, 300]) * 1000
            note = "LOAN DISB" if rng.random() < self.cue(0.9, 0.4) else ""
            ts = at(self._random_day(lo, hi, quiet), rng.randint(11, 16), rng.randint(0, 59))
            self._credit(ts, amount, "BANK_TRANSFER", self.lender, "non_business",
                         "business loan disbursed by a lender", note)
        for _ in range(2):
            if rng.random() < 0.3 * nb:
                value = rng.choice([100_000, 200_000, 300_000, 500_000])
                amount = round(value * (1 - rng.uniform(0.07, 0.25)), -1)
                note = "chit prize" if rng.random() < self.cue(0.7, 0.2) else ""
                ts = at(self._random_day(lo, hi, quiet), rng.randint(11, 17), rng.randint(0, 59))
                self._credit(ts, amount, rng.choice(["IMPS", "BANK_TRANSFER"]), self.chit,
                             "non_business", "chit fund payout (chit value less auction discount)",
                             note)
        for fest in C.GIFT_FESTIVALS:
            if not lo <= fest <= hi:
                continue
            for _ in range(poisson(rng, 0.8 * nb)):
                d = fest + timedelta(days=rng.randint(-1, 1))
                if d in quiet or not lo <= d <= hi:
                    continue
                if rng.random() < self.cue(0.8, 0.35):
                    amount = rng.choice([501, 1001, 1001, 2001])
                else:
                    amount = rng.choice([500, 1000, 1500, 2000])
                note = rng.choice(["gift", "happy festival"]) if rng.random() < self.cue(0.4, 0.1) else ""
                channel = "UPI_INTENT" if rng.random() < 0.7 else "UPI_QR"
                ts = at(d, rng.randint(8, 21), rng.randint(0, 59))
                self._credit(ts, amount, channel, rng.choice(self.friends), "non_business",
                             "festival gift from a friend", note)
        for _ in range(poisson(rng, 1.2 * nb)):
            amount = rng.randint(4, 40) * 500
            note = "returned" if rng.random() < self.cue(0.5, 0.1) else ""
            ts = self._off_hours_ts(self._random_day(lo, hi, quiet), rng.random() < 0.4)
            self._credit(ts, amount, "UPI_INTENT", rng.choice(self.friends), "non_business",
                         "hand loan repaid by a friend", note)
        if rng.random() < 0.15 * nb:
            amount = rng.randint(4, 12) * 5000
            note = "deposit refund" if rng.random() < self.cue(0.6, 0.2) else ""
            ts = at(self._random_day(lo, hi, quiet), rng.randint(10, 18), rng.randint(0, 59))
            self._credit(ts, amount, "IMPS", self.landlord, "non_business",
                         "rent deposit returned by a former landlord", note)
        if rng.random() < 0.2 * nb:
            amount = rng.randint(800, 4500) * 10 + rng.randint(1, 9)
            note = "claim settlement" if rng.random() < self.cue(0.8, 0.3) else ""
            ts = at(self._random_day(lo, hi, quiet), rng.randint(11, 17), rng.randint(0, 59))
            self._credit(ts, amount, "BANK_TRANSFER", self.insurer, "non_business",
                         "insurance claim settled", note)

    def gen_month_topups(self):
        rng = self.rng
        month = date(self.start.year, self.start.month, 1)
        while month <= self.end:
            if rng.random() < min(1.0, 0.8 * self.cfg["own_topups"]):
                d = month + timedelta(days=rng.randint(0, 4))
                if self.start <= d <= self.end and d not in self.quiet_dates:
                    step = 5000 if rng.random() < self.cue(0.8, 0.4) else 1000
                    amount = rng.randint(1, 5) * 5000 if step == 5000 else rng.randint(5, 25) * 1000
                    source = self.own["savings" if rng.random() < 0.7 else "personal_upi"]
                    channel = "IMPS" if rng.random() < 0.2 else "UPI_INTENT"
                    ts = at(d, rng.randint(8, 10), rng.randint(0, 59))
                    self._credit(ts, amount, channel, source, "inter_account",
                                 "month-start top-up from the owner's own account")
            month = date(month.year + (month.month == 12), month.month % 12 + 1, 1)

    # ------------------------------------------------------------ fraud

    def gen_fraud_chain(self, purpose: str, *, purchase_ts: datetime | None = None,
                        amount: int | None = None, lines: list[Line] | None = None,
                        channel: str | None = None, payer: Party | None = None,
                        lea: tuple[str, str, str] | None = None, event_ts: datetime | None = None,
                        ncrp_ack: str | None = None, case_ref: str | None = None,
                        scheme: str | None = None, hop_times: list[datetime] | None = None) -> Txn:
        """A victim is scammed; the money is layered through mules; the last mule buys goods here.

        purpose "freeze" ends in a lien on the whole account; "inquiry" ends in a police request
        for the transaction details with no freeze (the merchant is not told).
        """
        rng = self.rng
        chain_id = f"FC-{self.merchant_id}-{len(self.fraud_chains) + 1}"
        unit, state, city = lea or rng.choice(C.LEA_UNITS)
        if purchase_ts is None:
            lo = self.end - timedelta(days=60) if purpose == "freeze" else self.start + timedelta(days=30)
            day = self._random_day(lo, self.end - timedelta(days=7), self.quiet_dates)
            purchase_ts = at(day, rng.randint(10, 20), rng.randint(0, 59), rng.randint(0, 59))
        amount = amount or rng.choice([2750, 3600, 4200, 5100, 6480])
        payer = payer or self._person("mule", "mule_b", rng.choice(list(C.REGIONS.values())), 0.1)
        victim_first, victim_surname = self._name(rng.choice(list(C.REGIONS.values())))
        mule_a = self._person("mule", "mule_a", rng.choice(list(C.REGIONS.values())), 0.1)
        mule_c = self._person("mule", "mule_c", rng.choice(list(C.REGIONS.values())), 0.1)
        mule_d = self._person("mule", "mule_d", rng.choice(list(C.REGIONS.values())), 0.1)
        if hop_times:
            t_va, t_ab = hop_times
        else:
            t_ab = purchase_ts - timedelta(hours=rng.randint(20, 30), minutes=rng.randint(0, 59))
            t_va = t_ab - timedelta(hours=rng.randint(18, 30), minutes=rng.randint(0, 59))
        if lines is None:
            lines = self.basket_for_amount(amount)
        if channel is None:
            channel = "UPI_POS" if self.cfg["pos_share"] > 0 and rng.random() < 0.6 else "UPI_QR"
        sale = self.make_sale(purchase_ts, party=payer, lines=lines, channel=channel)
        sale.pinned = sale.locked = True
        sale.fraud_chain_id = chain_id
        sale.reason += "; the payer was a downstream mule (fraud-linked, but a genuine purchase)"
        self.pre.append(sale)

        ncrp_ack = ncrp_ack or f"SYN-{rng.randint(10**13, 10**14 - 1)}"
        case_ref = case_ref or f"SYN Cr. No. {rng.randint(100, 999)}/2026"
        chain = dict(
            chain_id=chain_id, purpose=purpose, scheme=scheme or rng.choice(C.FRAUD_SCHEMES),
            merchant_id=self.merchant_id,
            victim=dict(name=f"{victim_first} {victim_surname}", city=city, state=state),
            hops=[
                dict(layer=1, **{"from": f"{victim_first} {victim_surname}".upper()},
                     to=mule_a.name, to_handle=mule_a.handle, amount=50_000, ts=t_va),
                dict(layer=2, **{"from": mule_a.name}, to=payer.name, to_handle=payer.handle,
                     amount=20_000, ts=t_ab),
                dict(layer=2, **{"from": mule_a.name}, to=mule_c.name, to_handle=mule_c.handle,
                     amount=15_000, ts=t_ab + timedelta(minutes=7)),
                dict(layer=2, **{"from": mule_a.name}, to=mule_d.name, to_handle=mule_d.handle,
                     amount=12_000, ts=t_ab + timedelta(minutes=19)),
                dict(layer=3, **{"from": payer.name}, to=self.business_name.upper(),
                     to_handle="(this merchant)", amount=amount, ts=purchase_ts, credit=sale),
            ],
            lea=dict(unit=unit, state=state, city=city, ncrp_ack=ncrp_ack, case_ref=case_ref),
            note="The merchant's credit is a genuine sale to a downstream mule; provenance "
                 "(a sale) and fraud linkage are separate questions.",
        )
        self.fraud_chains.append(chain)

        authority = dict(unit=unit, state=state, city=city)
        if purpose == "freeze":
            ts = event_ts or at(purchase_ts.date() + timedelta(days=rng.randint(2, 5)), 9, 30)
            self.freeze_ts = ts
            self.events_pre.append(dict(
                type="lien_marked", ts=ts, freeze_type="debit_freeze", scope="entire account",
                authority=authority, ncrp_ack=ncrp_ack, case_ref=case_ref,
                disputed_amount=amount, disputed_date=purchase_ts.date().isoformat(),
                _disputed=sale,
                intimation="Lien marked by the bank on a law-enforcement request; the account "
                           "holder was not notified.",
            ))
        else:
            ts = event_ts or at(purchase_ts.date() + timedelta(days=rng.randint(3, 6)),
                                rng.randint(10, 16), rng.randint(0, 59))
            self.events_pre.append(dict(
                type="lea_inquiry", ts=ts, authority=authority, ncrp_ack=ncrp_ack,
                case_ref=case_ref, amount=amount, date=purchase_ts.date().isoformat(),
                _disputed=sale,
                request="Details of the transaction, the payer as seen by the PSP, and whether "
                        "goods or services were supplied.",
                confidentiality="Do not disclose this request to the account holder.",
            ))
        return sale

    # ------------------------------------------------------------ the ledger pass

    def run_pass(self):
        """Replay the year in time order: pay suppliers, top up from own accounts when short,
        refund and reverse, sweep to savings, and decline every debit once a lien is in place.

        Deterministic for a given set of pre-pass transactions, so a scenario can adjust sales
        and re-run it.
        """
        rng = random.Random(self.spec.seed * 7919 + 17)
        cfg = self.cfg
        created: list[Txn] = []
        rel: list[tuple[Txn, Txn, str]] = []
        declines: list[dict] = []
        heap: list = []
        order = itertools.count()

        def push(ts, kind, obj=None):
            heapq.heappush(heap, (ts, next(order), kind, obj))

        for t in self.pre:
            push(t.ts, "txn", t)
        forced = {ts.date() for ts in self.forced_supplier_times}
        d = self.start + timedelta(days=rng.randint(1, 3))
        while d <= self.end:
            if d not in self.quiet_dates and d not in forced:
                hour = rng.choice([10, 11, 12, 15, 16])
                push(at(d, hour, rng.randint(0, 59)), "supplier")
            d += timedelta(days=rng.randint(*cfg["supplier_gap"]))
        for ts in self.forced_supplier_times:
            push(ts, "supplier")
        for day in days(self.start, self.end):
            if day.weekday() == 6 and rng.random() < cfg["sweep_p"]:
                push(at(day, rng.randint(21, 23), rng.randint(0, 59)), "sweep")
            push(at(day, 23, 59, 59), "eod", day)

        balance = rng.randint(*cfg["opening_balance"])
        buffer = rng.randint(*cfg["buffer"])
        opening, day_cr, day_dr = balance, 0, 0
        sales_since = 0
        last_ts = at(self.start, 0)
        balances = []

        def frozen(ts):
            return self.freeze_ts is not None and ts >= self.freeze_ts

        def decline(ts, amount, channel, party, note):
            declines.append(dict(type="payment_declined", ts=ts, direction="DR", amount=amount,
                                 channel=channel, _party=party, reason_code="SYN-DEBIT-FREEZE",
                                 reason="Debit not allowed: account under lien / debit freeze",
                                 purpose=note))

        def ensure_funds(ts, need):
            nonlocal balance, day_cr
            if balance - buffer >= need:
                return
            shortfall = need - (balance - buffer)
            step = 5000 if rng.random() < self.cue(0.8, 0.4) else 1000
            amount = math.ceil(shortfall / step) * step
            top_ts = max(ts - timedelta(seconds=rng.randint(300, 2400)), last_ts + timedelta(seconds=1))
            source = self.own["savings" if rng.random() < 0.65 else "personal_upi"]
            channel = "IMPS" if rng.random() < 0.2 else "UPI_INTENT"
            t = Txn(self.merchant_id, top_ts, "CR", amount, channel, source,
                    label="inter_account", reason="top-up from the owner's own account just before "
                                                  "a supplier payment", tags={"inter_account"})
            created.append(t)
            balance += amount
            day_cr += amount

        def pay_supplier(ts, supplier, amount, retry=False):
            nonlocal balance, day_dr, sales_since
            if frozen(ts):
                note = "supplier payment"
                decline(ts, amount, "UPI_OUT", supplier, note)
                decline(ts + timedelta(minutes=rng.randint(3, 9)), amount, "UPI_OUT", supplier, note + " (retry)")
                decline(ts + timedelta(minutes=rng.randint(12, 25)), amount, "UPI_OUT", supplier, note + " (retry)")
                return
            ensure_funds(ts, amount)
            pay = Txn(self.merchant_id, ts, "DR", amount, "UPI_OUT", supplier,
                      note=rng.choice(["", "", "stock", "bill", "goods"]), tags={"supplier_payment"})
            created.append(pay)
            balance -= amount
            day_dr += amount
            if not retry:
                sales_since = 0
            if rng.random() < cfg["payout_fail_rate"]:
                rev_ts = ts + timedelta(minutes=rng.randint(1, 30))
                rev = Txn(self.merchant_id, rev_ts, "CR", amount, "UPI_REVERSAL", supplier,
                          orig=pay, label="refund_reversal", reason="failed payout reversed",
                          tags={"refund_reversal"})
                push(rev_ts, "created", rev)
                rel.append((rev, pay, "reversal_of"))
                push(rev_ts + timedelta(minutes=rng.randint(30, 90)), "retry", (supplier, amount))
            elif rng.random() < cfg["vendor_refund_rate"]:
                back = int(round(amount * rng.uniform(0.05, 0.30), -1))
                rd = ts.date() + timedelta(days=rng.randint(1, 3))
                while rd in self.quiet_dates:
                    rd += timedelta(days=1)
                rts = at(rd, rng.randint(10, 18), rng.randint(0, 59))
                if rd <= self.end and back > 0:
                    note = (rng.choice(["short supply", "crate return", "rate difference"])
                            if rng.random() < self.cue(0.7, 0.2) else "")
                    vr = Txn(self.merchant_id, rts, "CR", back,
                             rng.choice(["UPI_INTENT", "IMPS"]), supplier, note=note,
                             label="refund_reversal",
                             reason="supplier sent part of a payment back", tags={"refund_reversal"})
                    push(rts, "created", vr)
                    rel.append((vr, pay, "vendor_refund_for"))

        while heap:
            ts, _, kind, obj = heapq.heappop(heap)
            if ts.date() > self.end:
                continue
            if kind in ("txn", "created"):
                t = obj
                if kind == "created":
                    created.append(t)
                if t.direction == "CR":
                    balance += t.amount
                    day_cr += t.amount
                    if t.is_supply:
                        sales_since += t.amount
                else:
                    ensure_funds(ts, t.amount)
                    balance -= t.amount
                    day_dr += t.amount
            elif kind == "supplier":
                amount = int(round(sales_since * rng.uniform(*cfg["supplier_ratio"]), -1))
                if rng.random() < cfg["stock_up_p"]:
                    amount = int(round(amount * rng.uniform(1.8, 3.0), -1))
                if amount >= 1000 or (self.freeze_ts and ts.date() == self.freeze_ts.date()):
                    amount = max(amount, 1000)
                    pay_supplier(ts, rng.choice(self.suppliers), amount)
            elif kind == "retry":
                supplier, amount = obj
                pay_supplier(ts, supplier, amount, retry=True)
            elif kind == "sweep":
                if not frozen(ts) and balance > buffer + 10_000:
                    amount = int(round((balance - buffer) * rng.uniform(*cfg["sweep_share"]), -3))
                    sweep = Txn(self.merchant_id, ts, "DR", amount, "UPI_OUT", self.own["savings"],
                                tags={"sweep"})
                    created.append(sweep)
                    balance -= amount
                    day_dr += amount
            elif kind == "eod":
                balances.append(dict(date=obj, opening_balance=opening, credits=day_cr,
                                     debits=day_dr, closing_balance=balance))
                opening, day_cr, day_dr = balance, 0, 0
            last_ts = max(last_ts, ts)

        self.txns = sorted(self.pre + created, key=lambda t: (t.ts, t.direction))
        self.relationships = self.rel_pre + rel
        self.events = sorted(self.events_pre + declines, key=lambda e: e["ts"])
        self.balances = balances

    # ------------------------------------------------------------ tax events

    def gen_tax_events(self):
        rng = self.rng
        if self.spec.tax_notice:
            spec = self.spec.notice
            notice_date = spec.get("date") or date(2026, 8, rng.randint(10, 28))
            dept, office = C.TAX_OFFICES[self.place["state"]]
            gross = sum(t.amount for t in self.txns
                        if t.direction == "CR" and C.FY_START <= t.ts.date() <= C.FY_END)
            received = notice_date + timedelta(days=spec.get("received_after_days", rng.randint(2, 4)))
            self.notice = dict(
                reference=spec.get("reference") or f"SYN/CTD/2026-27/{rng.randint(100, 9999):05d}",
                date=notice_date, department=dept, office=f"{office}, {self.place['city']}",
                addressee=self.owner_name, business_name=self.business_name,
                address=f"{self.business_name}, {self.place['locality']}, {self.place['city']} "
                        f"{self.place['pincode']}, {self.place['state']}",
                period="FY 2025-26", period_from=C.FY_START, period_to=C.FY_END,
                claimed_turnover=gross, threshold=C.THRESHOLDS[self.cfg["supply_kind"]],
                basis="UPI receipts reported by payment aggregators",
                allegation="Receipts during the period exceed the registration threshold, and the "
                           "supplier has not obtained GST registration.",
                response_due=notice_date + timedelta(days=30),
                received_ts=at(received, rng.randint(18, 20), rng.randint(0, 59)),
            )
            self.events.append(dict(type="notice_served", ts=self.notice["received_ts"],
                                    _notice=True))
        if self.cfg["gst_status"] == "composition":
            quarters = [(date(2025, 4, 1), date(2025, 6, 30), date(2025, 7, 18)),
                        (date(2025, 7, 1), date(2025, 9, 30), date(2025, 10, 18)),
                        (date(2025, 10, 1), date(2025, 12, 31), date(2026, 1, 18)),
                        (date(2026, 1, 1), date(2026, 3, 31), date(2026, 4, 18))]
            under = set(rng.sample(range(4), 2))
            for i, (q_from, q_to, filed) in enumerate(quarters):
                true = sum(t.amount for t in self.txns if t.is_supply and q_from <= t.ts.date() <= q_to)
                factor = rng.uniform(0.70, 0.92) if i in under else rng.uniform(0.98, 1.0)
                declared = int(round(true * factor, -2))
                self.returns.append(dict(quarter=f"FY2025-26 Q{i + 1}", true_turnover=true,
                                         declared_turnover=declared, under_declared=i in under))
                self.events.append(dict(type="return_filed", ts=at(filed, 17, rng.randint(0, 59)),
                                        form="CMP-08", period=f"FY2025-26 Q{i + 1}",
                                        declared_turnover=declared))
        self.events.sort(key=lambda e: e["ts"])

    # ------------------------------------------------------------ merchant behaviour

    CONFUSION = {
        "taxable_supply": ["family"], "exempt_supply": ["family"],
        "personal_transfer": ["sale", "loan_or_gift", "own_money"],
        "inter_account": ["family"], "non_business": ["family", "sale"],
        "refund_reversal": ["sale"], "duplicate": ["sale"],
    }
    P_WRONG = {"taxable_supply": 0.01, "exempt_supply": 0.01, "personal_transfer": 0.04,
               "inter_account": 0.03, "non_business": 0.08, "refund_reversal": 0.06,
               "duplicate": 0.10}

    def gen_answers(self):
        """What this merchant would say if asked about each credit (hidden; for the harness)."""
        rng = random.Random(self.spec.seed * 104729 + 3)
        self.behaviour = dict(
            merchant_id=self.merchant_id, language=self.region["language"],
            answer_rate=0.93, p_not_sure=0.05, p_wrong=self.P_WRONG,
            delay_minutes=dict(median=40, sigma=1.0, cap=720), voice_share=0.35,
            text_share=0.05, correction_rate=0.35, correction_lag_days=[1, 20],
            reply_window="08:30-10:30",
            annotations_after_case=dict(count=[3, 8], truthful_share=1.0),
            note="An ordinary honest shopkeeper: answers most questions the same day, is "
                 "occasionally wrong, and sometimes corrects themselves later.",
        )
        for t in self.txns:
            if t.direction != "CR":
                continue
            row = dict(responds=rng.random() < 0.93, answer="", delay_minutes=0, mode="",
                       correction="", correction_lag_days=0)
            if row["responds"]:
                truthful = C.LABEL_TO_ANSWER[t.label]
                if rng.random() < 0.05:
                    row["answer"] = "not_sure"
                elif rng.random() < self.P_WRONG[t.label]:
                    row["answer"] = rng.choice(self.CONFUSION[t.label])
                    if rng.random() < 0.35:
                        row["correction"] = truthful
                        row["correction_lag_days"] = rng.randint(1, 20)
                else:
                    row["answer"] = truthful
                row["delay_minutes"] = min(720, int(math.exp(rng.gauss(math.log(40), 1.0))))
                r = rng.random()
                row["mode"] = "voice" if r < 0.35 else ("text" if r < 0.40 else "tap")
            self.answers[t] = row

    # ------------------------------------------------------------ cues

    def finalize(self):
        seen: dict[str, int] = {}
        owner_tokens = {self.owner_surname.upper()}
        for t in self.txns:
            if t.direction != "CR":
                continue
            cues = set(t.cues)
            if t.amount >= 500 and t.amount % 500 == 0:
                cues.add("round_amount")
            if t.ts.hour >= 22 or t.ts.hour < 7:
                cues.add("off_hours")
            if t.channel in P2P_CHANNELS:
                cues.add("p2p_channel")
            tokens = t.party.name.split()
            if t.party.role in ("family", "own") and owner_tokens & set(tokens):
                cues.add("surname_match")
            if any(len(tok) == 1 for tok in tokens):
                cues.add("abbreviated_name")
            if t.party.role == "own" and t.party.linked:
                cues.add("registered_own_account")
            if t.note:
                cues.add("note")
            if t.billed:
                cues.add("pos_bill")
            if t.orig is not None:
                cues.add("orig_linked")
            if seen.get(t.party.pid, 0) == 0:
                cues.add("first_time_payer")
            seen[t.party.pid] = seen.get(t.party.pid, 0) + 1
            t.cues = sorted(cues)

    # ------------------------------------------------------------ truth

    def truth(self) -> dict:
        credits = [t for t in self.txns if t.direction == "CR"]
        by_label = {label: dict(count=0, amount=0) for label in C.LABELS}
        for t in credits:
            by_label[t.label]["count"] += 1
            by_label[t.label]["amount"] += t.amount
        supply = sorted((t for t in credits if t.is_supply), key=lambda t: t.ts)
        exempt = sum(t.exempt_value for t in supply)
        taxable = sum(t.taxable_value for t in supply)
        threshold = C.THRESHOLDS[self.cfg["supply_kind"]]
        cum, crossing = 0, None
        for t in supply:
            cum += t.amount
            if cum > threshold:
                crossing = t.ts.date()
                break
        exclusively_exempt = taxable == 0 and exempt > 0
        gst_status = self.cfg["gst_status"]
        return dict(
            merchant_id=self.merchant_id, archetype=self.spec.archetype,
            difficulty=self.d, supply_kind=self.cfg["supply_kind"], gst_status=gst_status,
            language=self.region["language"],
            window=[self.start.isoformat(), self.end.isoformat()],
            gross_credits=sum(t.amount for t in credits), credit_count=len(credits),
            by_label=by_label, exempt_turnover=exempt, taxable_turnover=taxable,
            aggregate_turnover=exempt + taxable, registration_threshold=threshold,
            threshold_crossing_date=crossing.isoformat() if crossing else None,
            exclusively_exempt=exclusively_exempt,
            registration_required=(crossing is not None and not exclusively_exempt
                                   and gst_status == "unregistered"),
            already_registered=gst_status != "unregistered",
            own_accounts=[dict(relation=k, name=p.name, handle=p.handle, linked=p.linked,
                               counterparty_id=p.pid) for k, p in self.own.items()],
            family=[dict(relation=k, name=p.name, handle=p.handle, counterparty_id=p.pid)
                    for k, p in self.family.items()],
            suppliers=[dict(name=p.name, handle=p.handle, counterparty_id=p.pid)
                       for p in self.suppliers],
            declared_returns=self.returns,
            freeze_ts=self.freeze_ts.isoformat() if self.freeze_ts else None,
        )

    # ------------------------------------------------------------ build

    def build(self) -> World:
        self.setup_people()
        self.scenario.setup(self)
        self.gen_sales()
        self.gen_repeats()
        if self.spec.fraud_freeze:
            self.gen_fraud_chain("freeze")
        if self.spec.lea_inquiry:
            self.gen_fraud_chain("inquiry")
        if self.spec.target_turnover:
            self.calibrate_total(self.spec.target_turnover)
        self.scenario.after_sales(self)
        self.gen_duplicates()
        self.gen_family()
        self.gen_nonbusiness()
        self.gen_month_topups()
        self.scenario.after_money(self)
        self.scenario.ledger_pass(self)
        self.gen_tax_events()
        self.gen_answers()
        self.finalize()
        self.scenario.check(self)
        return self
