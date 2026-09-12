"""Phinite custom tool: project_threshold_breach.

Answers two different questions honestly:
  - has this merchant already crossed the registration threshold, and on what date?
  - at the current run rate, when will they?

Thresholds: Rs 40 lakh for a supplier of goods, Rs 20 lakh for services. Aggregate turnover
includes exempt supplies, so an exempt-heavy shop can cross it - except that a person dealing
*exclusively* in exempt goods is not liable to register at all (CGST s.23), which is exactly
the vegetable-vendor case. Both branches are reported.

Parameters: merchant_id (string, required), as_of (YYYY-MM-DD, optional - project using only
data up to this date), fy (string like "2025-26", optional).
Self-contained: paste this whole file into Dev Studio. Standard library only.
"""
import json
import urllib.parse
import urllib.request
from datetime import date, timedelta

SUPPLY = ("taxable_supply", "exempt_supply")


def _api(env, path, params=None, body=None, key="HISAAB_KEY"):
    base = (env.get("HISAAB_API") or "http://127.0.0.1:8000").rstrip("/")
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                 headers={"X-API-Key": env.get(key) or "", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main(inputs, env_variables):
    merchant_id = (inputs.get("merchant_id") or "").strip()
    if not merchant_id:
        return {"output": {"error": "merchant_id is required"}, "captured_variables": {}}
    fy = str(inputs.get("fy") or "2025-26")
    fy_start = date(int(fy.split("-")[0]), 4, 1)
    fy_end = date(fy_start.year + 1, 3, 31)
    as_of = date.fromisoformat(inputs["as_of"]) if inputs.get("as_of") else fy_end

    merchant = _api(env_variables, "/merchants/%s" % merchant_id)
    data = _api(env_variables, "/ledger/rollup", {"merchant_id": merchant_id,
                                                  "start": fy_start.isoformat(),
                                                  "end": as_of.isoformat()})
    services = merchant.get("supply_kind") == "services"
    threshold = 2000000 if services else 4000000

    daily = {}
    taxable = exempt = 0
    for row in data["rollup"]:
        if row["label"] not in SUPPLY:
            continue
        daily[row["day"]] = daily.get(row["day"], 0) + row["amount"]
        if row["label"] == "taxable_supply":
            taxable += row["amount"]
        else:
            exempt += row["amount"]

    cumulative, crossed_on, running = [], None, 0
    for day in sorted(daily):
        running += daily[day]
        cumulative.append((day, running))
        if crossed_on is None and running > threshold:
            crossed_on = day

    exclusively_exempt = taxable == 0 and exempt > 0
    turnover = running
    days_observed = (as_of - fy_start).days + 1
    projected_on, lead_days, run_rate = None, None, 0
    if crossed_on is None and turnover > 0:
        # Run rate from the trailing 60 days, which tracks a growing shop better than the year's mean.
        recent = [amt for day, amt in daily.items() if date.fromisoformat(day) > as_of - timedelta(days=60)]
        run_rate = (sum(recent) / 60.0) if recent else turnover / max(1, days_observed)
        if run_rate > 0:
            need = threshold - turnover
            hit = as_of + timedelta(days=int(need / run_rate) + 1)
            if hit <= fy_end:
                projected_on = hit.isoformat()
                lead_days = (hit - as_of).days

    if exclusively_exempt:
        verdict = ("This shop deals exclusively in exempt goods, so registration is not required "
                   "however high turnover goes (CGST s.23). Keep the evidence of what is sold.")
    elif crossed_on:
        verdict = ("Aggregate turnover crossed Rs %d on %s. Registration is required - CGST s.25 "
                   "gives 30 days from becoming liable. Confirm with a CA before filing." % (threshold, crossed_on))
    elif projected_on:
        verdict = ("At the current rate, aggregate turnover reaches Rs %d around %s, about %d days "
                   "away. Nothing to do yet; plan for registration." % (threshold, projected_on, lead_days))
    else:
        verdict = "Aggregate turnover is Rs %d, below the Rs %d threshold, and not on course to cross it this year." % (turnover, threshold)

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
