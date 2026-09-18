"""Demo scenarios: pinned payments, calibration and the assertions that keep the story true.

Sahana Stores (Kannada, Bengaluru) carries every beat of the demo. Maurya Sabzi Bhandar (Hindi,
Lucknow) is the exclusively-exempt vegetable seller who crosses Rs 40 lakh and still does not need
to register, which is the Haveri story.

The answer key is written to data/demo/hidden/demo_scenario.json. Product code must read IDs from
there, never hard-code them: they change whenever the generator changes.
"""

from __future__ import annotations

import random
from datetime import date, datetime, timedelta

from . import catalog as C
from .world import Line, Party, Scenario, Txn, World, at


def basket(*rows: tuple[str, float, int]) -> list[Line]:
    """Explicit basket lines: (item, quantity, line amount)."""
    out = []
    for item, qty, amount in rows:
        name, hsn, exempt, _basis, _group, unit, _prices, _qtys = C.ITEM_BY_NAME[item]
        out.append(Line(name, hsn, exempt, qty, unit, amount))
    return out


def credits_between(w: World, start: datetime, end: datetime) -> list[Txn]:
    return [t for t in w.txns if t.direction == "CR" and start <= t.ts < end]


class SahanaScenario(Scenario):
    name = "sahana_stores"

    ATTEST_DAY = date(2026, 3, 10)
    QUIET = (date(2026, 3, 8), date(2026, 3, 9))
    CROSSING = date(2026, 3, 14)
    REPLAY_AS_OF = date(2026, 1, 31)
    FREEZE_TS = at(date(2026, 3, 24), 9, 30)
    DISPUTED_TS = at(date(2026, 3, 21), 19, 47)
    DECOY_TS = at(date(2026, 3, 18), 18, 12)
    WEEK_CREDITS = 339
    AMOUNT_WINDOW = (date(2026, 3, 14), date(2026, 3, 28))
    NOTICE = dict(reference="SYN/CTD/2026-27/00417", date=date(2026, 8, 20), received_after_days=2)

    def setup(self, w: World):
        w.quiet_dates |= set(self.QUIET)
        w.no_dup_dates |= {date(2026, 3, 13), date(2026, 3, 14), date(2026, 3, 15)}
        w.family["spouse"] = Party("MANJUNATH GOWDA", "manjunath.gowda56@okhdfcbank", "family",
                                   "spouse")
        w.own["savings"] = Party("SAHANA GOWDA", "sahanagow29@oksbi", "own", "savings",
                                 linked=True)
        w.forced_supplier_times.append(at(date(2026, 3, 24), 9, 41))
        self.raghu = Party("RAGHU SHETTY", "raghu.shetty77@okicici", "customer", "regular")
        self.mule = Party("SUNITHA MURTHY", "sunitha.m1987@okaxis", "mule", "mule_b")
        self.unknown = Party("K NAGARAJ", "97XXXXXX43@ybl", "customer", "walk_in")

    # -------------------------------------------------------------- sales

    def after_sales(self, w: World):
        # 8-9 Mar must surface exactly three questions: no P2P sales, no large unbilled baskets.
        for t in w.pre:
            if "sale" not in t.tags or t.ts.date() not in self.QUIET:
                continue
            if t.channel == "UPI_INTENT":
                t.channel, t.terminal = "UPI_QR", "SBX01"
            while not t.billed and t.amount >= 2500:
                t.lines = w._basket(bulk=False)
                w.label_sale(t)
            t.locked = True

        def pin(ts, party, lines, channel):
            sale = w.make_sale(ts, party=party, lines=lines, channel=channel)
            sale.pinned = sale.locked = True
            w.pre.append(sale)
            return sale

        self.raghu_before = [
            pin(at(date(2026, 1, 24), 17, 5), self.raghu, basket(
                ("Onion", 20, 800), ("Tomato", 15, 600), ("Potato", 20, 600),
                ("Coriander & greens", 30, 300)), "UPI_QR"),
            pin(at(date(2026, 2, 17), 18, 20), self.raghu, basket(
                ("Onion", 25, 1000), ("Tomato", 20, 800), ("Carrot", 10, 500), ("Beans", 8, 560),
                ("Coriander & greens", 24, 240)), "UPI_QR"),
        ]
        self.raghu_sale = pin(at(date(2026, 3, 9), 16, 40), self.raghu, basket(
            ("Onion", 30, 1200), ("Tomato", 25, 1000), ("Potato", 30, 900), ("Carrot", 12, 600),
            ("Beans", 10, 750), ("Coriander & greens", 40, 400)), "UPI_QR")
        self.raghu_sale.reason = ("bulk vegetables for a family function from a customer who has "
                                  "bought twice before")
        self.tiny = pin(at(date(2026, 3, 8), 21, 52), self.unknown, basket(
            ("Coriander & greens", 1, 15), ("Lemon", 1, 8)), "UPI_INTENT")
        self.tiny.reason = "coriander and a lemon, paid straight to the VPA by a first-time payer"

        before_decoy = {}
        for t in w.pre:
            if "sale" in t.tags and t.party.relation == "regular" and t.ts < self.DECOY_TS:
                before_decoy[t.party] = before_decoy.get(t.party, 0) + 1
        regular = max(before_decoy, key=before_decoy.get)
        self.decoy = pin(self.DECOY_TS, regular, basket(
            ("Loose rice", 25, 1500), ("Cooking oil", 5, 850), ("Onion", 10, 400), ("Potato", 10, 300),
            ("Eggs", 60, 420), ("Tomato", 8, 320), ("Sugar", 5, 250), ("Tea powder", 1, 160)),
            "UPI_QR")
        self.decoy.reason = "monthly provisions from a regular customer (same amount as the disputed payment)"

        self.disputed = w.gen_fraud_chain(
            "freeze", purchase_ts=self.DISPUTED_TS, amount=4200, channel="UPI_POS", payer=self.mule,
            lines=basket(("Onion", 12, 480), ("Potato", 10, 340), ("Carrot", 6, 360), ("Eggs", 90, 630),
                         ("Loose rice", 25, 1550), ("Tomato", 12, 480), ("Beans", 4, 360)),
            lea=("Cyber Crime Police Station, Hyderabad", "Telangana", "Hyderabad"),
            event_ts=self.FREEZE_TS, ncrp_ack="SYN-31703260045812", case_ref="SYN Cr. No. 412/2026",
            scheme="part-time job task scam",
            hop_times=[at(date(2026, 3, 19), 11, 12), at(date(2026, 3, 20), 18, 40)])
        self.inquiry_sale = w.gen_fraud_chain(
            "inquiry", purchase_ts=at(date(2026, 2, 6), 12, 15), amount=1850, channel="UPI_QR",
            lines=basket(("Loose rice", 10, 650), ("Onion", 10, 400), ("Cooking oil", 2, 380),
                         ("Tomato", 5, 250), ("Eggs", 24, 170)),
            lea=("Cyber Crime Police Station, Jaipur", "Rajasthan", "Jaipur"),
            event_ts=at(date(2026, 2, 11), 11, 5), scheme="fake investment app")

        self.k = w.calibrate_crossing(self.CROSSING, C.THRESHOLDS["goods"])

    # -------------------------------------------------------------- other money

    def after_money(self, w: World):
        self.own_money = w._credit(at(date(2026, 3, 8), 23, 4), 15_000, "UPI_INTENT",
                                   w.own["savings"], "inter_account",
                                   "the owner's own money, from their linked savings account")
        self.spouse_money = w._credit(at(date(2026, 3, 9), 13, 20), 7_500, "UPI_QR",
                                      w.family["spouse"], "personal_transfer",
                                      "household money from the owner's spouse, scanned at the shop QR "
                                      "like a customer")
        for t in (self.own_money, self.spouse_money):
            t.pinned = t.locked = True

        # Only the disputed payment and the decoy may be exactly Rs 4,200 around the freeze.
        lo, hi = self.AMOUNT_WINDOW
        linked = {id(a) for a, b, _ in w.rel_pre} | {id(b) for a, b, _ in w.rel_pre}
        for t in w.pre:
            if (t.direction == "CR" and t.amount == 4200 and lo <= t.ts.date() <= hi
                    and t not in (self.disputed, self.decoy)):
                if "sale" not in t.tags or id(t) in linked:
                    raise AssertionError(f"cannot move a linked Rs 4,200 credit at {t.ts}")
                t.lines[-1].amount += 10
                w.label_sale(t)

    # -------------------------------------------------------------- ledger pass

    def ledger_pass(self, w: World):
        """Re-run the pass, adding or removing small walk-in sales until the week before the
        freeze holds exactly 339 credits (the figure in the Round 1 deck)."""
        start, end = self.FREEZE_TS - timedelta(days=7), self.FREEZE_TS
        rng = random.Random(w.spec.seed * 31 + 5)
        curve = C.HOUR_CURVES[w.cfg["hour_curve"]]
        for _ in range(12):
            w.run_pass()
            diff = self.WEEK_CREDITS - len(credits_between(w, start, end))
            if diff == 0:
                return
            linked = {id(a) for a, b, _ in w.rel_pre} | {id(b) for a, b, _ in w.rel_pre}
            if diff < 0:
                removable = [t for t in w.pre if "sale" in t.tags and not t.locked
                             and t.party.relation == "walk_in" and t.channel == "UPI_QR"
                             and id(t) not in linked and start <= t.ts < end]
                for t in rng.sample(removable, min(-diff, len(removable))):
                    w.pre.remove(t)
            else:
                for _ in range(diff):
                    while True:
                        day = start.date() + timedelta(days=rng.randint(0, 7))
                        ts = at(day, rng.choices(range(24), weights=curve)[0], rng.randint(0, 59),
                                rng.randint(0, 59))
                        if start <= ts < end:
                            break
                    sale = w.make_sale(ts, party=w._person("customer", "walk_in"), channel="UPI_QR",
                                       bulk=False)
                    while sale.amount == 4200:
                        sale.lines[-1].amount += 10
                        w.label_sale(sale)
                    sale.locked = True
                    w.pre.append(sale)
        raise AssertionError("could not settle the week before the freeze at 339 credits")

    # -------------------------------------------------------------- checks

    def check(self, w: World):
        truth = w.truth()
        assert truth["threshold_crossing_date"] == self.CROSSING.isoformat(), truth["threshold_crossing_date"]
        assert truth["registration_required"]

        week = credits_between(w, self.FREEZE_TS - timedelta(days=7), self.FREEZE_TS)
        assert len(week) == self.WEEK_CREDITS, len(week)

        quiet = [t for t in w.txns if t.direction == "CR" and t.ts.date() in self.QUIET]
        non_sales = {t for t in quiet if not t.is_supply}
        assert non_sales == {self.own_money, self.spouse_money}, [(t.ts, t.label) for t in non_sales]
        p2p = {t for t in quiet if t.channel in ("UPI_INTENT", "IMPS", "BANK_TRANSFER")}
        assert p2p == {self.own_money, self.tiny}, [(t.ts, t.amount) for t in p2p]
        big_unbilled = {t for t in quiet if t.is_supply and not t.billed and t.amount >= 2500}
        assert big_unbilled == {self.raghu_sale}, [(t.ts, t.amount) for t in big_unbilled]
        for a in quiet:
            for b in quiet:
                if a is not b and a.party is b.party and a.amount == b.amount:
                    assert abs((a.ts - b.ts).total_seconds()) > 1800, (a.ts, b.ts, a.amount)

        lo, hi = self.AMOUNT_WINDOW
        same = {t for t in w.txns if t.direction == "CR" and t.amount == 4200 and lo <= t.ts.date() <= hi}
        assert same == {self.disputed, self.decoy}, [(t.ts, t.label) for t in same]
        assert self.disputed.billed and self.disputed.label == "exempt_supply"

        prior = [t for t in w.txns if t.party is self.raghu and t.ts < self.raghu_sale.ts]
        assert len(prior) == 2
        decoy_prior = [t for t in w.txns if t.party is self.decoy.party and t.ts < self.decoy.ts]
        assert len(decoy_prior) >= 8, len(decoy_prior)

        declines = [e for e in w.events if e["type"] == "payment_declined"]
        first = [e for e in declines if e["ts"] < self.FREEZE_TS + timedelta(minutes=45)]
        assert len(first) >= 3, len(first)
        assert all(e["ts"] >= self.FREEZE_TS for e in declines)

    # -------------------------------------------------------------- answer key

    def describe(self, w: World, ref) -> dict:
        truth = w.truth()
        credits = [t for t in w.txns if t.direction == "CR"]
        week = credits_between(w, self.FREEZE_TS - timedelta(days=7), self.FREEZE_TS)
        quiet = [t for t in credits if t.ts.date() in self.QUIET]
        balance_before = next(b["closing_balance"] for b in w.balances
                              if b["date"] == self.FREEZE_TS.date() - timedelta(days=1))
        declines = [e for e in w.events if e["type"] == "payment_declined"]
        as_of = [t for t in credits if t.is_supply and t.ts.date() <= self.REPLAY_AS_OF]
        lo, hi = self.AMOUNT_WINDOW
        return dict(
            merchant_id=w.merchant_id, business_name=w.business_name, owner=w.owner_name,
            language="kn",
            beat_freeze=dict(
                lien_ts=self.FREEZE_TS.isoformat(), ncrp_ack="SYN-31703260045812",
                case_ref="SYN Cr. No. 412/2026",
                authority="Cyber Crime Police Station, Hyderabad (Telangana)",
                disputed=ref(self.disputed), decoy=ref(self.decoy),
                same_amount_credits=[ref(t) for t in sorted(
                    (t for t in credits if t.amount == 4200 and lo <= t.ts.date() <= hi),
                    key=lambda t: t.ts)],
                credits_in_7_days_before_freeze=len(week),
                closing_balance_day_before_freeze=balance_before,
                declined_debits_after_freeze=len(declines),
                first_decline_ts=declines[0]["ts"].isoformat() if declines else None,
                expected="Isolate the disputed credit by UTR and, independently, by amount and "
                         "date; list the decoy without choosing it; never assert innocence.",
            ),
            beat_ordinary_tuesday=dict(
                attestation_date=self.ATTEST_DAY.isoformat(), lookback_days=2,
                credits_on_those_days=len(quiet),
                expected_questions=[ref(self.own_money), ref(self.spouse_money), ref(self.raghu_sale)],
                left_alone=[ref(self.tiny)],
                raghu_prior_purchases=[ref(t) for t in self.raghu_before],
            ),
            beat_warning=dict(
                threshold=C.THRESHOLDS["goods"], true_crossing_date=self.CROSSING.isoformat(),
                replay_as_of=self.REPLAY_AS_OF.isoformat(),
                turnover_as_of_replay=sum(t.amount for t in as_of),
            ),
            beat_notice=dict(
                reference=w.notice["reference"], date=w.notice["date"].isoformat(),
                claimed_turnover=w.notice["claimed_turnover"],
                breakdown={label: v["amount"] for label, v in truth["by_label"].items()},
                exempt_turnover=truth["exempt_turnover"], taxable_turnover=truth["taxable_turnover"],
                aggregate_turnover=truth["aggregate_turnover"],
                not_turnover=truth["gross_credits"] - truth["aggregate_turnover"],
                registration_required=truth["registration_required"],
                expected="The claim counts every credit as turnover and is wrong; the merchant did "
                         "cross Rs 40 lakh on 14 Mar 2026 and must register.",
            ),
            beat_lea_inquiry=dict(
                credit=ref(self.inquiry_sale),
                event_ts=next(e["ts"].isoformat() for e in w.events if e["type"] == "lea_inquiry"),
                expected="Answer through an officer; never message the merchant about it.",
            ),
            calibration=dict(sales_scale_factor=round(self.k, 4)),
        )


class LucknowScenario(Scenario):
    name = "maurya_sabzi_bhandar"

    TARGET_TURNOVER = 4_600_000
    NOTICE = dict(reference="SYN/ST-LKO/2026-27/01982", date=date(2026, 8, 26), received_after_days=3)

    def after_sales(self, w: World):
        self.k = w.calibrate_total(self.TARGET_TURNOVER)

    def check(self, w: World):
        truth = w.truth()
        assert truth["aggregate_turnover"] > C.THRESHOLDS["goods"], truth["aggregate_turnover"]
        assert truth["taxable_turnover"] == 0 and truth["exclusively_exempt"]
        assert truth["threshold_crossing_date"] is not None
        assert not truth["registration_required"]

    def describe(self, w: World, ref) -> dict:
        truth = w.truth()
        return dict(
            merchant_id=w.merchant_id, business_name=w.business_name, owner=w.owner_name,
            language="hi",
            beat_exempt_notice=dict(
                reference=w.notice["reference"], date=w.notice["date"].isoformat(),
                claimed_turnover=w.notice["claimed_turnover"],
                aggregate_turnover=truth["aggregate_turnover"],
                exempt_turnover=truth["exempt_turnover"], taxable_turnover=truth["taxable_turnover"],
                threshold_crossing_date=truth["threshold_crossing_date"],
                registration_required=False,
                expected="Above Rs 40 lakh, but every sale is exempt (fresh vegetables and fruit), so "
                         "registration is not required (CGST s.23). The notice counts non-sale "
                         "money too.",
            ),
            calibration=dict(sales_scale_factor=round(self.k, 4)),
        )
