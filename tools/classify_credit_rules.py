# ENV_VARS: ["HISAAB_API", "HISAAB_KEY"]
"""Phinite custom tool 3/13 — classify_credit_rules.

The deterministic pre-filter. It settles the credits that need no judgement and returns
label=null for the rest, which is what the Provenance agent should spend an LLM call on.
Every answer carries its evidence, so the Phinite trace shows why.

Two things it deliberately will not do:
  - call an ordinary sale "personal" or the reverse on thin signals: it returns null;
  - ask the merchant to split exempt from taxable on a QR sale with no itemised bill.
    That split is not identifiable per credit, only in aggregate, so it is apportioned
    from the shop's billed sales and flagged as an estimate rather than burning the day's
    attestation budget on an unanswerable question.

Inputs
    merchant_id (string, required)
    txn_id      (string, required)

Output
    label (or null), confidence, evidence, and ask_merchant.

Env
    HISAAB_API, HISAAB_KEY

Paste the whole file into Dev Studio. Standard library only; imports nothing local.
"""
import json
import urllib.error
import urllib.parse
import urllib.request

HOUSEHOLD_WORDS = ("mane", "home", "amma", "school", "rent", "gas", "emi", "kharchu", "for you")
NON_BUSINESS_WORDS = ("loan", "chit", "advance", "claim", "disb", "settlement")
BUSINESS_SUFFIX = ("TRADERS", "WHOLESALE", "AGENCIES", "DISTRIBUTORS", "FINANCE", "CHITS",
                   "INSURANCE", "LTD", "PVT", "AGENTS", "SUPPLIES")
EXEMPT_CATEGORIES = ("vegetable", "fruits", "milk")
ASK_BELOW = 0.75
MATERIAL_NON_SALE = 10000   # a big credit held out of turnover must be the merchant's call
UNUSUAL_SALE = 3000         # a large sale from a near-stranger, with no bill to back it
MIN_ASK = 500               # below this, a tap costs the merchant more than the error does
TIMEOUT = 20


def _get(env, path, params=None):
    base = (env.get("HISAAB_API") or "").rstrip("/")
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"X-Hisaab-Key": env.get("HISAAB_KEY") or ""})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def context(env, merchant_id, txn_id):
    """Assemble one credit's full picture from the service's separate reads."""
    credit = _get(env, "/credits/" + urllib.parse.quote(txn_id))
    hist = _get(env, "/payer_history", {"merchant_id": merchant_id, "txn_id": txn_id})
    twins = _get(env, "/credits/%s/twins" % urllib.parse.quote(txn_id))
    catalog = _get(env, "/hsn")
    exempt_by_item = {(h["item"], h["hsn"]): bool(h["exempt"])
                      for h in (catalog if isinstance(catalog, list) else [])}
    c = dict(credit)
    c["bill"] = [{"item": ln["item"], "hsn": ln["hsn"], "line_amount": ln["line_amount"],
                  "exempt": exempt_by_item.get((ln["item"], ln["hsn"]), False)}
                 for ln in (credit.get("bill_lines") or [])]
    c["refunded_by"] = twins.get("refunds") or []
    return {
        "credit": c,
        "prior_credits": {"count": max(0, (hist.get("credit_count") or 0) - 1),
                          "total": hist.get("credit_total") or 0},
        "channels_used": sorted((hist.get("channels") or {}).keys()),
        "merchant_has_paid_this_payer": {"count": hist.get("merchant_paid_count") or 0},
        "twin_payments_within_30min": twins.get("twins") or [],
        "is_linked_own_account": bool(hist.get("handle_is_linked_own_account")),
    }


def _r(label, confidence, why, **flags):
    return label, confidence, [why], flags


def _should_ask(label, confidence, h):
    """Confidence is not the only reason to ask. Size is: a wrong tag on a big credit is
    what a notice or a freeze actually turns on, so material ones get confirmed even when
    the rules are sure."""
    amount = h["credit"]["amount"]
    if amount < MIN_ASK:
        return False, ""
    if label is None or confidence < ASK_BELOW:
        return True, "the evidence does not settle it"
    supply = label in ("taxable_supply", "exempt_supply")
    if not supply and amount >= MATERIAL_NON_SALE:
        return True, "large credit kept out of turnover - worth the merchant's confirmation"
    if supply and amount >= UNUSUAL_SALE and h["prior_credits"]["count"] <= 3 \
            and not h["credit"].get("bill"):
        return True, "unusually large payment from someone who has barely paid before"
    return False, ""


def _decide(h, merchant, mix):
    """-> (label|None, confidence, [evidence], flags)"""
    c = h["credit"]
    name = (c.get("counterparty_name") or "").upper()
    note = (c.get("note") or "").lower()
    p2p = c["channel"] in ("UPI_INTENT", "IMPS", "BANK_TRANSFER")
    bill = c.get("bill") or []
    owner = (merchant.get("owner_name") or "").split()
    surname_match = bool(owner) and owner[-1].upper() in name

    if c["channel"] == "UPI_REVERSAL":
        return _r("refund_reversal", 0.97, "credited back on the reversal rail")
    if h["is_linked_own_account"]:
        return _r("inter_account", 0.95, "payer handle is an account the merchant registered as their own")
    if name and name == (merchant.get("owner_name") or "").upper():
        return _r("inter_account", 0.88, "payer name is exactly the owner's name")
    if h["merchant_has_paid_this_payer"]["count"] > 0 and any(w in name for w in BUSINESS_SUFFIX):
        return _r("refund_reversal", 0.85, "money coming back from a counterparty the merchant pays")
    if c.get("refunded_by") and h["twin_payments_within_30min"]:
        return _r("duplicate", 0.92, "identical payment minutes apart and this one was refunded")
    if any(w in note for w in NON_BUSINESS_WORDS):
        return _r("non_business", 0.85, 'payment note says "%s"' % c["note"])
    if c["channel"] == "BANK_TRANSFER" and any(w in name for w in BUSINESS_SUFFIX):
        return _r("non_business", 0.8, "bank transfer from a finance, chit or insurance counterparty")
    if p2p and c["amount"] % 100 == 1 and c["amount"] <= 5101:
        return _r("non_business", 0.7, "shagun-style amount ending in 1, typical of a gift")
    if bill:
        exempt = sum(l["line_amount"] for l in bill if l.get("exempt"))
        label = "exempt_supply" if exempt * 2 > c["amount"] else "taxable_supply"
        return _r(label, 0.95, "itemised bill: %s" % ", ".join(
            "%s (%s)" % (l["item"], l["hsn"]) for l in bill))

    # --- genuinely ambiguous: worth a question ---
    if p2p and surname_match and h["prior_credits"]["count"] >= 2:
        return _r("personal_transfer", 0.6, "shares the owner's surname, pays directly, has paid before")
    if p2p and any(w in note for w in HOUSEHOLD_WORDS):
        return _r("personal_transfer", 0.6, 'household note: "%s"' % c["note"])
    if h["twin_payments_within_30min"]:
        return _r("duplicate", 0.5, "identical payment from the same payer within 30 minutes, no refund seen")
    if p2p:
        return _r(None, 0.0, "paid straight to the VPA, but nothing says whose money it is")

    # A QR scan usually means a customer - but not from someone who also sends money
    # directly, or who shares the owner's surname. Family scanning the shop QR is the case
    # that quietly inflates turnover, so never call it a sale on the channel alone.
    if surname_match and h["prior_credits"]["count"] >= 2:
        return _r("personal_transfer", 0.55,
                  "scanned the shop QR like a customer, but shares the owner's surname and has "
                  "paid %d times before" % h["prior_credits"]["count"])
    if any(ch in ("UPI_INTENT", "IMPS", "BANK_TRANSFER") for ch in h.get("channels_used", [])):
        return _r(None, 0.0, "this payer has also sent money straight to the VPA, so a QR payment "
                             "from them is not necessarily a sale")

    # --- an ordinary sale. It IS a supply; only the exempt/taxable split is estimated. ---
    share = mix.get("exempt_share_of_billed_value")
    if share is None:
        category = (merchant.get("category") or "").lower()
        label = "exempt_supply" if any(w in category for w in EXEMPT_CATEGORIES) else "taxable_supply"
        return _r(label, 0.8, "QR sale at a %s with no itemised bills to sample"
                  % (merchant.get("category") or "shop"), exempt_taxable_is_aggregate_estimate=True)
    label = "exempt_supply" if share > 0.5 else "taxable_supply"
    return _r(label, 0.8, "QR sale with no bill; %.0f%% of this shop's billed value is exempt, so "
                          "the split is an aggregate estimate, not a per-credit fact" % (share * 100),
              exempt_taxable_is_aggregate_estimate=True)


def main(inputs, env_variables):
    merchant_id = str(inputs.get("merchant_id") or "").strip()
    txn_id = str(inputs.get("txn_id") or "").strip()
    if not merchant_id or not txn_id:
        return {"output": {"error": "merchant_id and txn_id are both required"},
                "captured_variables": {}}
    try:
        h = context(env_variables, merchant_id, txn_id)
        merchant = _get(env_variables, "/merchants/" + urllib.parse.quote(merchant_id))
        mix = _get(env_variables, "/merchant_mix", {"merchant_id": merchant_id})
    except urllib.error.HTTPError as e:
        return {"output": {"error": "HTTP %s classifying %s" % (e.code, txn_id)},
                "captured_variables": {}}

    label, confidence, evidence, flags = _decide(h, merchant, mix)
    ask, ask_reason = _should_ask(label, confidence, h)
    out = {
        "txn_id": txn_id,
        "label": label,
        "confidence": round(confidence, 2),
        "evidence": evidence,
        "needs_judgement": label is None,
        "ask_merchant": ask,
        "ask_reason": ask_reason,
        "credit": {k: h["credit"].get(k) for k in ("ts", "amount", "channel",
                                                   "counterparty_name", "note")},
    }
    out.update(flags)
    return {"output": out, "captured_variables": {"rule_label": label or "unclassified",
                                                  "rule_confidence": out["confidence"],
                                                  "rule_ask_merchant": ask}}


# Phinite injects only the variables declared in the ENV_VARS header above, so a tool
# cannot read a key it does not ask for. commit_attestation is the only tool that
# declares HISAAB_ATTEST_KEY, which is the permission boundary enforced a second way.
#
# Phinite reads one of "capture_variables" / "captured_variables" and ignores the other.
# Which one is not documented and the Dev Studio tool test echoes the return verbatim,
# so it cannot settle it. Returning both costs nothing and removes the risk of variables
# silently failing to pass between nodes.
_main = main


def main(inputs, env_variables):  # noqa: F811
    result = _main(inputs, env_variables)
    if isinstance(result, dict) and "captured_variables" in result:
        result.setdefault("capture_variables", result["captured_variables"])
    return result
