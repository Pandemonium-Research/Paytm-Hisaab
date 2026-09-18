"""Stateful wire-contract double for testing B workflows in a real local n8n.

Runs on :8300 inside core's container, separately from its real API/database.
This verifies B orchestration only; it is not the joint persistence checkpoint.
"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime
from urllib.parse import urlparse, parse_qs
import json
import threading

NOW = "2026-03-10T02:00:00+05:30"
state = {"proposals": [], "questions": [], "claims": [], "messages": [],
         "histories": [], "pages": [], "windows": [], "polls": [], "question_reads": [], "packs": {}, "deliveries": []}
roles = {"/ledger/proposals": "provenance", "/skills/classify-rules": "provenance",
         "/skills/select-questions": "provenance", "/ledger/questions": "conversation",
         "/ledger/claims": "conversation", "/assistant/outbound": "conversation", "/packs": "evidence"}


def aware(value):
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        raise ValueError("A bare date would have to guess IST or UTC")
    return moment


def txn(tid, amount, bill=False):
    return {"txn_id": tid, "merchant_id": "MID_TEST", "amount": amount,
            "ts": "2026-03-09T12:00:00+05:30", "counterparty_id": "P" + tid,
            "counterparty_name": "TEST PAYER", "counterparty_handle": "test@upi",
            "channel": "UPI_POS" if bill else "IMPS", "direction": "CR",
            "pos_bill_id": "B" + tid if bill else None, "terminal_id": "POS01" if bill else None,
            "utr": "60000000000" + tid[-1], "orig_txn_id": None, "note": ""}


credits = [{"transaction": txn("T1", 500, True), "machine_label": None},
           {"transaction": txn("T2", 15000), "machine_label": None},
           {"transaction": txn("T3", 7500), "machine_label": None}]
old = {"transaction": txn("T0", 12000), "machine_label": None}
old['transaction']['ts'] = '2026-03-07T23:59:59+05:30'
at_end = {"transaction": txn("T4", 12000), "machine_label": None}
at_end['transaction']['ts'] = '2026-03-10T00:00:00+05:30'
credits = [old, *credits, at_end]


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, data, status=200):
        raw = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        u = urlparse(self.path)
        q = parse_qs(u.query)
        if u.path == "/test/state":
            return self.reply(state)
        if u.path.startswith("/merchants/"):
            return self.reply({"merchant_id": "MID_TEST", "preferred_language": "kn-IN", "supply_kind": "goods"})
        if u.path == "/credits":
            # Core applies the half-open [from, to) itself and rejects a bare date, so the double
            # has to as well: otherwise WF10 could ask for the wrong window and still look right.
            try:
                window = [aware(q[key][0]) if key in q else None for key in ("from", "to")]
            except ValueError:
                return self.reply({"detail": "from and to need a UTC offset"}, 422)
            since, until = window
            if since and until and since >= until:
                return self.reply({"detail": "The credit window must be [from, to) with from before to."}, 422)
            cursor = q.get("cursor", [None])[0]
            if cursor is None:
                state["windows"].append({"from": q.get("from", [None])[0], "to": q.get("to", [None])[0],
                                         "limit": q.get("limit", [None])[0]})
            inside = [c for c in credits
                      if (since is None or aware(c["transaction"]["ts"]) >= since)
                      and (until is None or aware(c["transaction"]["ts"]) < until)]
            if q.get("limit", ["50"])[0] == "1":
                return self.reply({"items": inside[:1], "as_of": NOW, "next_cursor": None})
            state["pages"].append(cursor)
            page = inside[2:] if cursor == "page2" else inside[:2]
            for c in page:
                found = next((p for p in state["proposals"] if p["txn_id"] == c["transaction"]["txn_id"]), None)
                c["machine_label"] = found["proposal"]["label"] if found else None
            return self.reply({"items": page, "as_of": NOW,
                               "next_cursor": None if cursor == "page2" or len(inside) <= 2 else "page2"})
        if u.path.startswith("/payers/"):
            state["histories"].append({"path": u.path, "as_of": q.get("as_of", [None])[0]})
            return self.reply({"strictly_prior_credit_count": 0, "merchant_has_paid_them": False,
                               "own_account_cue": False, "surname_cue": False, "payer_facts": []})
        if u.path == "/app/home":
            return self.reply({"as_of": NOW, "merchant_id": "MID_TEST"})
        if u.path == "/app/questions":
            state['question_reads'].append(q.get('merchant', [None])[0])
            answered = {c["claim"]["question_id"] for c in state["claims"]}
            return self.reply({"items": [{"question_id": p["question"]["question_id"], "txn_id": p["txn_id"],
                "question": p["question"]["text"], "language": p["question"]["language"]}
                for p in state["questions"] if p["question"]["question_id"] not in answered]})
        if u.path.startswith("/app/officer/cases/"):
            cid = u.path.rsplit("/", 1)[-1]
            state["polls"].append(cid)
            pack = state["packs"].get(cid, {})
            return self.reply({"case": {"case_id": cid}, "pack_id": pack.get("pack_id"),
                               "status": pack.get("status", "open")})
        return self.reply({"detail": "Missing mock route " + u.path}, 404)

    def do_POST(self):
        path = urlparse(self.path).path
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
        if path == "/test/reset":
            for value in state.values():
                value.clear()
            return self.reply({"reset": True})
        if path == "/test/shutdown":
            self.reply({"stopped": True})
            threading.Thread(target=self.server.shutdown, daemon=True).start()
            return
        if path == "/test/decision":
            state["packs"][body["case_id"]]["status"] = body["status"]
            return self.reply({"updated": True})
        role = roles.get(path, "officer" if path.startswith("/outbox/") else None)
        if role and self.headers.get("X-Hisaab-Key") != "dev-" + role:
            return self.reply({"detail": "Wrong role for " + path}, 403)
        if path == "/skills/classify-rules":
            c = body["credits"][0]
            result = None if c["txn_id"] == "T2" else {"txn_id": c["txn_id"], "label": "taxable_supply",
                "confidence": 1 if c["has_bill"] else 0.6, "rule_id": "test-rule", "ask": not c["has_bill"], "reason": "Visible evidence"}
            return self.reply({"results": [{"txn_id": c["txn_id"], "result": result}]})
        if path == "/ledger/proposals":
            state["proposals"].append(body)
            return self.reply({"entry": {"payload": body["proposal"], "sim_at": body["sim_at"]}})
        if path == "/skills/select-questions":
            candidates = [c for c in body["candidates"] if not c["has_bill"] and c["confidence"] < 0.75]
            available = max(0, 3 - len(state["questions"]))
            return self.reply({"selected": [{"txn_id": c["txn_id"], "payer_id": c["payer_id"], "priority": 1,
                "expires_at": "2026-03-17T02:00:00+05:30"} for c in candidates[:available]],
                "expired_txn_ids": [], "remaining_daily_budget": available - min(len(candidates), available)})
        if path == "/ledger/questions":
            state["questions"].append(body)
            return self.reply({"entry": {"payload": body["question"]}})
        if path == "/ledger/claims":
            if any(c["claim"]["question_id"] == body["claim"]["question_id"] for c in state["claims"]):
                return self.reply({"detail": "Already answered"}, 409)
            state["claims"].append(body)
            return self.reply({"entry": {"payload": body["claim"]}, "payer_fact_updated": True})
        if path == "/assistant/outbound":
            state["messages"].append(body)
            return self.reply({"published": True, "message_id": str(len(state["messages"]))})
        if path == "/packs":
            pid = "PACK-" + body["case_id"]
            state["packs"].setdefault(body["case_id"], {"pack_id": pid, "status": "awaiting_approval"})
            return self.reply({"pack_id": pid, "case_id": body["case_id"]})
        if path.startswith("/outbox/"):
            pid = path.split("/")[2]
            pack = next((p for p in state["packs"].values() if p["pack_id"] == pid), None)
            if not pack or pack["status"] != "approved":
                return self.reply({"detail": "Approval required"}, 403)
            pack["status"] = "sent"
            state["deliveries"].append({"pack_id": pid, **body})
            return self.reply({"sent": True, "simulated": True, "ledger_entry": {"sim_at": NOW}})
        return self.reply({"detail": "Missing mock route " + path}, 404)


if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", 8300), Handler).serve_forever()
