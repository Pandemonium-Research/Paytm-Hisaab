"""Phinite custom tool 8/13 — project_threshold_breach.

Answers two different questions honestly:
  - has this merchant already crossed the registration threshold, and on what date?
  - at the current run rate, when will they?

Thresholds: Rs 40 lakh for a supplier of goods, Rs 20 lakh for services. Aggregate turnover
includes exempt supplies, so an exempt-heavy shop can cross it - except that a person
dealing *exclusively* in exempt goods is not liable to register at all (CGST s.23), which
is exactly the vegetable-vendor case. Both branches are reported.

Inputs
    merchant_id (string, required)
    as_of       (string, optional)  YYYY-MM-DD - project using only data up to this date
    fy          (string, optional)  default 2025-26

Env
    HISAAB_API, HISAAB_KEY

Paste the whole file into Dev Studio. Standard library only.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

SUPPLY = ("taxable_supply", "exempt_supply")
TIMEOUT = 30


def _get(env, path, params=None):
    base = (env.get("HISAAB_API") or "").rstrip("/")
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"X-Hisaab-Key": env.get("HISAAB_KEY") or ""})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main(inputs, env_variables):
    merchant_id = str(inputs.get("merchant_id") or "").strip()
    if not merchant_id:
        return {"output": {"error": "merchant_id is required"}, "captured_variables": {}}
    fy = str(inputs.get("fy") or "2025-26")
    fy_start = date(int(fy.split("-")[0]), 4, 1)
    fy_end = date(fy_start.year + 1, 3, 31)
    as_of = date.fromisoformat(str(inputs["as_of"])) if inputs.get("as_of") else fy_end

    try:
        merchant = _get(env_variables, "/merchants/" + urllib.parse.quote(merchant_id))
        roll = _get(env_variables, "/ledger/rollup", {
            "merchant_id": merchant_id, "date_from": fy_start.isoformat(),
            "date_to": as_of.isoformat(), "by_day": "true"})
    except urllib.error.HTTPError as e:
        return {"output": {"error": "HTTP %s projecting threshold" % e.code}, "captured_variables": {}}

    services = merchant.get("supply_kind") == "services"
    threshold = 2000000 if services else 4000000

    daily = {}
    for day, labels in (roll.get("by_day") or {}).items():
        supply = sum(v for k, v in labels.items() if k in SUPPLY)
        if supply:
            daily[day] = supply

    def total(label):
        buckets = (roll.get("by_label") or {}).get(label) or {}
        return sum((buckets.get(s) or {}).get("amount", 0) for s in ("attested", "proposed"))

    taxable, exempt = total("taxable_supply"), total("exempt_supply")
    cumulative, crossed_on, running = [], None, 0
    for day in sorted(daily):
        running += daily[day]
        cumulative.append([day, running])
        if crossed_on is None and running > threshold:
            crossed_on = day

    turnover = running
    exclusively_exempt = taxable == 0 and exempt > 0
    days_observed = max(1, (as_of - fy_start).days + 1)
    projected_on, lead_days, run_rate = None, None, 0.0
    if crossed_on is None and turnover > 0:
        # Trailing 60 days tracks a growing shop better than the year's mean.
        recent = [amt for day, amt in daily.items()
                  if date.fromisoformat(day) > as_of - timedelta(days=60)]
        run_rate = (sum(recent) / 60.0) if recent else turnover / float(days_observed)
        if run_rate > 0:
            hit = as_of + timedelta(days=int((threshold - turnover) / run_rate) + 1)
            if hit <= fy_end:
                projected_on = hit.isoformat()
                lead_days = (hit - as_of).days

    if exclusively_exempt:
        verdict = ("This shop deals exclusively in exempt goods, so registration is not required "
                   "however high turnover goes (CGST s.23). Keep the evidence of what is sold.")
    elif crossed_on:
        verdict = ("Aggregate turnover crossed Rs %d on %s. Registration is required - CGST s.25 "
                   "allows 30 days from becoming liable. Have a CA confirm before filing."
                   % (threshold, crossed_on))
    elif projected_on:
        verdict = ("At the current rate, aggregate turnover reaches Rs %d around %s, about %d days "
                   "away. Nothing to do today; plan for registration." % (threshold, projected_on, lead_days))
    else:
        verdict = ("Aggregate turnover is Rs %d, below the Rs %d threshold, and not on course to "
                   "cross it this year." % (turnover, threshold))

    out = {
        "merchant_id": merchant_id,
        "as_of": as_of.isoformat(),
        "financial_year": fy,
        "threshold": threshold,
        "threshold_basis": "services (Rs 20L)" if services else "goods (Rs 40L)",
        "aggregate_turnover_to_date": turnover,
        "taxable_supplies": taxable,
        "exempt_supplies": exempt,
        "exclusively_exempt": exclusively_exempt,
        "already_crossed_on": crossed_on,
        "projected_crossing_date": projected_on,
        "lead_time_days": lead_days,
        "daily_run_rate": round(run_rate, 2),
        "registration_required": bool(crossed_on) and not exclusively_exempt,
        "verdict": verdict,
        "cumulative_series": cumulative[-30:],
        "caveat": "Computed on attested and proposed digital receipts only; cash is not included. "
                  "This is a calculation, not advice - a CA signs off.",
    }
    return {"output": out, "captured_variables": {
        "threshold_crossed_on": crossed_on or "", "projected_crossing_date": projected_on or "",
        "aggregate_turnover": turnover, "registration_required": out["registration_required"]}}
