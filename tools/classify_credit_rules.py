"""Phinite custom tool: classify_credit_rules.

The deterministic pre-filter. It settles the credits that need no judgement and returns
label=null for the rest, which is what the Provenance agent should spend an LLM call on.
Every answer carries its evidence, so the trace shows why.

Two things it deliberately will not do:
  - call an ordinary sale "personal" or vice versa on thin signals: it returns null instead;
  - ask the merchant to split exempt from taxable on a QR sale with no itemised bill. That
    split is not identifiable per credit, only in aggregate, so it is flagged as an estimate
    rather than burning the day's attestation budget on an unanswerable question.

Parameters: merchant_id (string, required), txn_id (string, required).
Self-contained: paste this whole file into Dev Studio. Standard library only.
"""
import json
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


def _api(env, path, params=None, body=None, key="HISAAB_KEY"):
    base = (env.get("HISAAB_API") or "http://127.0.0.1:8000").rstrip("/")
    url = base + path + ("?" + urllib.parse.urlencode(params) if params else "")
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if body is not None else "GET",
                                 headers={"X-API-Key": env.get(key) or "", "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _r(label, confidence, why, **flags):
    return label, confidence, [why], flags


def _should_ask(label, confidence, h):
    """Confidence is not the only reason to ask. Size is: a wrong tag on a big credit is what
    a notice or a freeze actually turns on, so material ones get confirmed even when the rules
    are sure."""
    amount = h["credit"]["amount"]
    if amount < MIN_ASK:
        return False, ""
    if label is None or confidence < ASK_BELOW:
        return True, "the evidence does not settle it"
    supply = label in ("taxable_supply", "exempt_supply")
    if not supply and amount >= MATERIAL_NON_SALE:
        return True, "large credit kept out of turnover - worth the merchant's confirmation"
    if supply and amount >= UNUSUAL_SALE and h["prior_credits"]["count"] <= 3 \
            and not (h["credit"].get("bill")):
        return True, "unusually large payment from someone who has barely paid before"
    return False, ""


def _decide(h, merchant, mix):
    """-> (label|None, confidence, [evidence], flags)"""
    c = h["credit"]
    name = (c.get("counterparty_name") or "").upper()
    note = (c.get("note") or "").lower()
    p2p = c["channel"] in ("UPI_INTENT", "IMPS", "BANK_TRANSFER")
    bill = c.get("bill") or []

    if c["channel"] == "UPI_REVERSAL":
        return _r("refund_reversal", 0.97, "credited back on the reversal rail")
    if h["is_linked_own_account"]:
        return _r("inter_account", 0.95, "payer handle is an account the merchant linked as their own")
    if name and name == (merchant.get("owner_name") or "").upper():
        return _r("inter_account", 0.88, "payer name is exactly the owner's name")
    if h["merchant_has_paid_this_payer"]["count"] > 0 and any(w in name for w in BUSINESS_SUFFIX):
        return _r("refund_reversal", 0.85, "money coming back from a counterparty the merchant pays")
    if c.get("refunded_by") and h["twin_payments_within_30min"]:
        return _r("duplicate", 0.92, "identical payment minutes apart and this one was refunded")
    if any(w in note for w in NON_BUSINESS_WORDS):
        return _r("non_business", 0.85, 'payment note says "%s"' % c["note"])
    if c["channel"] == "BANK_TRANSFER" and any(w in name for w in BUSINESS_SUFFIX):
        return _r("non_business", 0.8, "bank transfer from a finance/chit/insurance counterparty")
    if p2p and c["amount"] % 100 == 1 and c["amount"] <= 5101:
        return _r("non_business", 0.7, "shagun-style amount (ends in 1), typical of a gift")
    if bill:
        exempt = sum(l["line_amount"] for l in bill if l.get("exempt"))
        label = "exempt_supply" if exempt * 2 > c["amount"] else "taxable_supply"
        return _r(label, 0.95, "itemised bill: %s" % ", ".join(
            "%s (%s)" % (l["item"], l["hsn"]) for l in bill))

    # --- genuinely ambiguous: worth a question ---
    if p2p and h["owner_surname_in_payer_name"] and h["prior_credits"]["count"] >= 2:
        return _r("personal_transfer", 0.6, "shares the owner's surname, pays directly, has paid before")
    if p2p and any(w in note for w in HOUSEHOLD_WORDS):
        return _r("personal_transfer", 0.6, 'household note: "%s"' % c["note"])
    if h["twin_payments_within_30min"]:
        return _r("duplicate", 0.5, "identical payment from the same payer within 30 minutes, no refund seen")
    if p2p:
        return _r(None, 0.0, "paid directly to the VPA, but nothing says whose money it is")

    # A QR scan usually means a customer - but not from someone who also sends money directly,
    # or who shares the owner's surname. Family scanning the shop QR is the case that quietly
    # inflates turnover, so never call it a sale on the strength of the channel alone.
    if h["owner_surname_in_payer_name"] and h["prior_credits"]["count"] >= 2:
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
        if any(w in category for w in EXEMPT_CATEGORIES):
            return _r("exempt_supply", 0.8, "QR sale at a %s shop with no itemised bills to sample"
                      % merchant.get("category"), exempt_taxable_is_aggregate_estimate=True)
        return _r("taxable_supply", 0.8, "QR sale at a %s shop with no itemised bills to sample"
                  % merchant.get("category"), exempt_taxable_is_aggregate_estimate=True)
    label = "exempt_supply" if share > 0.5 else "taxable_supply"
    return _r(label, 0.8, "QR sale with no bill; %.0f%% of this shop's billed value is exempt, so "
                          "the split is an aggregate estimate, not a per-credit fact" % (share * 100),
              exempt_taxable_is_aggregate_estimate=True)


def main(inputs, env_variables):
    merchant_id = (inputs.get("merchant_id") or "").strip()
    txn_id = (inputs.get("txn_id") or "").strip()
    if not merchant_id or not txn_id:
        return {"output": {"error": "merchant_id and txn_id are required"}, "captured_variables": {}}
    h = _api(env_variables, "/payer_history", {"merchant_id": merchant_id, "txn_id": txn_id})
    merchant = _api(env_variables, "/merchants/%s" % merchant_id)
    mix = _api(env_variables, "/merchant_mix", {"merchant_id": merchant_id})

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
        "credit": {k: h["credit"][k] for k in ("ts", "amount", "channel", "counterparty_name", "note")},
    }
    out.update(flags)
    return {"output": out, "captured_variables": {"rule_label": label or "unclassified",
                                                  "rule_confidence": out["confidence"]}}
