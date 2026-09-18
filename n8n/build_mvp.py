"""Generate the MVP workflows using built-in n8n nodes; no provider keys in JSON.

Run python n8n/build_mvp.py after editing, then n8n/cli.py import --activate.
WF30 and WF31 retain their signed WhatsApp path and gain the app path here.
"""
from pathlib import Path
import json
import uuid

ROOT = Path(__file__).resolve().parent
ROLES = {
    "provenance": ("hisaabLocalProv01", "hisaab core provenance (local)"),
    "conversation": ("hisaabLocalConv01", "hisaab core conversation (local)"),
    "app": ("hisaabLocalApp001", "hisaab core app (local)"),
    "evidence": ("hisaabLocalEvid01", "hisaab core evidence (local)"),
    "officer": ("hisaabLocalOffi01", "hisaab core officer (local)"),
    "sarvam": ("hisaabLocalSarv01", "hisaab sarvam (local fakes)"),
    "webhook": ("hisaabWebhook001", "hisaab core webhook (local)"),
}


class Workflow:
    def __init__(self, wid, name):
        self.data = dict(id=wid, name=name, active=False,
                         settings={"executionOrder": "v1"}, nodes=[], connections={})

    def node(self, name, kind, params=None, version=1, role=None, **extra):
        node = dict(id=str(uuid.uuid5(uuid.NAMESPACE_URL, self.data["id"] + name)),
                    name=name, type="n8n-nodes-base." + kind, typeVersion=version,
                    position=[len(self.data["nodes"]) * 220, 0], parameters=params or {}, **extra)
        if role:
            cid, cname = ROLES[role]
            node["credentials"] = {"httpHeaderAuth": {"id": cid, "name": cname}}
        self.data["nodes"].append(node)
        return name

    def code(self, name, code):
        return self.node(name, "code", {"jsCode": code}, 2)

    def http(self, name, path, role, body=None, query=None, **extra):
        params = dict(url=path if path.startswith("=") else "http://core:8000" + path,
                      authentication="genericCredentialType", genericAuthType="httpHeaderAuth",
                      options={"timeout": 30000})
        if body:
            params.update(method="POST", sendBody=True, specifyBody="json", jsonBody=body)
        if query:
            params.update(sendQuery=True, queryParameters={"parameters": [
                {"name": k, "value": v} for k, v in query.items()]})
        return self.node(name, "httpRequest", params, 4.2, role, **extra)

    def test(self, name, expression, value="true"):
        return self.node(name, "if", {"conditions": {"options": {
            "caseSensitive": True, "typeValidation": "loose", "version": 2},
            "conditions": [{"id": name, "leftValue": expression, "rightValue": value,
                            "operator": {"type": "string", "operation": "equals"}}],
            "combinator": "and"}, "options": {}}, 2)

    def webhook(self, name, path):
        return self.node(name, "webhook", {"httpMethod": "POST", "path": path,
            "authentication": "headerAuth", "responseMode": "onReceived", "options": {}},
            2, "webhook", webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, path)))

    def link(self, source, dest, output=0):
        main = self.data["connections"].setdefault(source, {"main": []})["main"]
        while len(main) <= output:
            main.append([])
        main[output].append({"node": dest, "type": "main", "index": 0})

    def chain(self, *names):
        for source, dest in zip(names, names[1:]):
            self.link(source, dest)

    def save(self, filename):
        (ROOT / "workflows" / filename).write_text(
            json.dumps(self.data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def wf10():
    w = Workflow("hisaabWF10mvp001", "hisaab/WF10 nightly-provenance")
    w.webhook("Nightly webhook", "hisaab/wf10-nightly")
    w.node("02:00 IST", "scheduleTrigger", {"rule": {"interval": [
        {"field": "cronExpression", "expression": "0 2 * * *"}]}}, 1.2)
    w.code("Run context", """
const item = $input.first().json;
// The 02:00 trigger carries a timestamp and no body: that is the one run allowed to say nothing.
const scheduled = !item.body && item.timestamp !== undefined;
const input = item.body || (scheduled ? {} : item);
if (input.mode === 'seed') throw new Error('Full-year seed is deferred; use a single live-mode run');
// An empty body used to start a real run against the default merchant, so probing whether the
// webhook had registered classified a whole window and left the ledger part-labelled.
if (!scheduled && !input.merchant_id && !input.merchant && !input.as_of) throw new Error('WF10 needs merchant_id or as_of; an empty body will not start a run');
return [{json: {merchant_id: input.merchant_id || input.merchant || 'MID_DEMO_SAHANA',
  as_of: input.as_of || null, channel: input.channel || 'app', to: input.to || null,
  // `to` is the WhatsApp recipient. The classification window is window_from/window_to, kept
  // separate on purpose: reusing `to` for both sent the reply to a date string.
  window_from: input.window_from || input.from || null, window_to: input.window_to || null}}];
""")
    w.http("Merchant", "={{ 'http://core:8000/merchants/' + encodeURIComponent($json.merchant_id) }}", "provenance")
    # One row, read for its echoed as_of only: the window defaults are relative to the IST day
    # start of business time, and the 02:00 trigger arrives without one. Asking the wall clock
    # instead would classify whichever window the laptop happened to be in. It names Run context
    # explicitly because this node's own input is the merchant, which carries no time.
    w.http("Business time", "/credits", "provenance", query={
        "merchant": "={{ $('Run context').first().json.merchant_id }}", "limit": "1"})
    w.code("Credit window", r"""
const state = $('Run context').first().json;
const as_of = state.as_of || $input.first().json.as_of;
// The one place the IST rule lives. The chain stores UTC and the screens answer IST, so a bare
// date is resolved here, once, and core is only ever sent instants.
const day = new Date(as_of).toLocaleDateString('en-CA', {timeZone:'Asia/Kolkata'});
const cutoff = new Date(day + 'T00:00:00+05:30');
const instant = value => new Date(/^\d{4}-\d{2}-\d{2}$/.test(value) ? value + 'T00:00:00+05:30' : value).getTime();
const start = state.window_from ? instant(state.window_from) : cutoff.getTime() - 2 * 86400000;
const end = state.window_to ? instant(state.window_to) : cutoff.getTime();
if (!Number.isFinite(start) || !Number.isFinite(end) || start >= end || end > new Date(as_of).getTime()) throw new Error('Credit window must be [from, to) at or before as_of');
return [{json: {...state, as_of, window_from: new Date(start).toISOString(),
  window_to: new Date(end).toISOString(), cursor: null, credits: [], cursors: []}}];
""")
    w.code("Page request", """
let state;
try { state = $('Collect page').item.json; } catch { state = $('Credit window').first().json; }
return [{json: state}];
""")
    # Core applies the half-open [from, to) itself, so a run reads its own window instead of
    # paging the whole history and discarding it: 1 call and 68 credits here, against 61 calls
    # and 12,097 credits before, which was most of the classification run.
    w.http("Read credits", "/credits", "provenance", query={
        "merchant": "={{ $json.merchant_id }}", "limit": "200",
        "as_of": "={{ $json.as_of }}", "from": "={{ $json.window_from }}",
        "to": "={{ $json.window_to }}", "cursor": "={{ $json.cursor || undefined }}"})
    w.code("Collect page", """
const state = $('Page request').item.json;
const page = $input.first().json;
if (page.next_cursor && state.cursors.includes(page.next_cursor)) throw new Error('Repeated credit cursor');
// The cursor stays inside the window, so this pages a busy window, not the history.
return [{json: {...state, credits: [...state.credits, ...page.items], cursor: page.next_cursor,
  cursors: [...state.cursors, page.next_cursor].filter(Boolean)}}];
""")
    w.test("More credits?", "={{ String(Boolean($json.cursor)) }}")
    w.code("Unlabelled credits", """
const state = $input.first().json;
const seen = new Set();
const credits = state.credits.filter(c => !c.machine_label &&
  new Date(c.transaction.ts) <= new Date(state.as_of) &&
  !seen.has(c.transaction.txn_id) && seen.add(c.transaction.txn_id));
return credits.map(credit => ({json: {credit, state}}));
""")
    w.node("Each credit", "splitInBatches", {"batchSize": 1, "options": {}}, 3)
    w.http("Strictly prior history", "={{ 'http://core:8000/payers/' + encodeURIComponent($json.credit.transaction.counterparty_id) + '/history' }}",
           "provenance", query={"merchant": "={{ $json.state.merchant_id }}", "as_of": "={{ $json.credit.transaction.ts }}"})
    w.code("Classification input", """
const item = $('Each credit').item.json;
const t = item.credit.transaction, h = $input.first().json;
const labels = ['taxable_supply','exempt_supply','personal_transfer','inter_account','non_business','refund_reversal','duplicate','unclassified'];
const fact = (h.payer_facts || []).find(f => labels.includes(f.value));
return [{json: {...item, history: h, classify: {merchant_id: item.state.merchant_id,
  as_of: item.state.as_of, credits: [{txn_id: t.txn_id, amount: t.amount,
    channel: t.channel, counterparty_id: t.counterparty_id, counterparty_name: t.counterparty_name,
    note: t.note || '', has_bill: Boolean(t.pos_bill_id), prior_credit_count: h.strictly_prior_credit_count,
    merchant_has_paid_them: h.merchant_has_paid_them, own_account_cue: h.own_account_cue,
    surname_cue: h.surname_cue, payer_fact: fact?.value || null}]}}}];
""")
    w.http("Classify rules", "/skills/classify-rules", "provenance", "={{ JSON.stringify($json.classify) }}")
    w.code("Rule result", """
const item = $('Classification input').item.json;
const result = $input.first().json.results.find(r => r.txn_id === item.credit.transaction.txn_id);
if (!result) throw new Error('Classification response omitted the requested transaction');
return [{json: {...item, rule: result.result}}];
""")
    w.test("Rule settled?", "={{ String(Boolean($json.rule)) }}")
    w.code("Rule proposal", """
const item = $input.first().json;
return [{json: {...item, proposal: {label: item.rule.label, source: 'rule',
  rule_id: item.rule.rule_id, confidence: item.rule.confidence, reason: item.rule.reason,
  evidence_refs: item.credit.transaction.pos_bill_id ? [item.credit.transaction.pos_bill_id] : [], memory_refs: []}}}];
""")
    schema = json.loads((ROOT / "schemas" / "hard-case-label.json").read_text(encoding="utf-8"))
    prompt = (ROOT.parent / "prompts" / "hard-case-label.v1.txt").read_text(encoding="utf-8")
    w.code("Hard-case request", """
const item = $input.first().json;
return [{json: {...item, request: {model: 'sarvam-105b', temperature: 0,
  messages: [{role: 'system', content: __PROMPT__},
    {role: 'user', content: JSON.stringify({credit: item.credit.transaction, history: item.history})}],
  response_format: {type: 'json_schema', json_schema: {name: 'HardCaseLabel', strict: true, schema: __SCHEMA__}}}}}];
""".replace("__PROMPT__", json.dumps(prompt)).replace("__SCHEMA__", json.dumps(schema)))
    w.http("Sarvam hard case (local fake)", "=http://fakes:8200/sarvam/v1/chat/completions", "sarvam",
           "={{ JSON.stringify($json.request) }}", onError="continueRegularOutput")
    w.code("Validate agent proposal", """
const item = $('Hard-case request').item.json;
const labels = ['taxable_supply','exempt_supply','personal_transfer','inter_account','non_business','refund_reversal','duplicate','unclassified'];
const evidence = ['rules_output','payer_history','bill','device_geo','credit_fields'];
let answer;
try {
  answer = JSON.parse($input.first().json.choices[0].message.content);
  if (Object.keys(answer).some(k => !['label','confidence','reason_en','evidence_used'].includes(k)) ||
      !labels.includes(answer.label) || typeof answer.confidence !== 'number' ||
      !Number.isFinite(answer.confidence) || answer.confidence < 0 || answer.confidence > 1 ||
      typeof answer.reason_en !== 'string' || !answer.reason_en.trim() || answer.reason_en.length > 400 ||
      !Array.isArray(answer.evidence_used) || answer.evidence_used.some(e => !evidence.includes(e))) throw new Error('Invalid HardCaseLabel');
} catch {
  answer = {label: 'unclassified', confidence: 0, reason_en: 'Model response unavailable or invalid; ask the merchant.', evidence_used: []};
}
return [{json: {...item, proposal: {label: answer.label, source: 'agent', model: 'sarvam-105b',
  prompt_version: 'hard-case-label.v1', confidence: Math.min(answer.confidence, 0.85),
  reason: answer.reason_en, evidence_refs: answer.evidence_used.includes('bill') && item.credit.transaction.pos_bill_id ? [item.credit.transaction.pos_bill_id] : [], memory_refs: []}}}];
""")
    w.http("Persist proposal", "/ledger/proposals", "provenance", "={{ JSON.stringify({merchant_id: $json.state.merchant_id, txn_id: $json.credit.transaction.txn_id, proposal: $json.proposal, sim_at: $json.state.as_of}) }}")
    w.code("Question candidate", """
// Use the persisted proposal, not a second model inference.
const entry = $input.first().json.entry;
const item = $('Rule result').item.json, t = item.credit.transaction;
return [{json: {txn_id: t.txn_id, payer_id: t.counterparty_id, amount: t.amount,
  label: entry.payload.label, confidence: entry.payload.confidence,
  strictly_prior_credit_count: item.history.strictly_prior_credit_count,
  has_bill: Boolean(t.pos_bill_id), payer_fact_known: item.history.payer_facts.length > 0,
  proposed_at: entry.sim_at}}];
""")
    w.code("Classification complete", """
// Loop's done output contains one candidate per credit. Collapse it before a shared read:
// otherwise HTTP Request sends the same app/questions call once per credit, in parallel.
return [{json: {merchant_id: $('Run context').first().json.merchant_id}}];
""")
    w.http("Open questions", "/app/questions", "app", query={"merchant": "={{ $json.merchant_id }}"})
    w.code("Selection request", """
const state = $('Collect page').last().json;
const open = $('Open questions').first().json.items;
const dateKey = new Date(state.as_of).toLocaleDateString('en-CA', {timeZone:'Asia/Kolkata'});
const merchant = $('Merchant').first().json;
const candidates = $('Each credit').all(0).map(i => i.json);
// Budget proximity only; registration and forecasts remain core's threshold skill.
const aggregate = state.credits.reduce((sum, c) => {
  const label = c.effective_label || candidates.find(p => p.txn_id === c.transaction.txn_id)?.label;
  return sum + (['taxable_supply','exempt_supply'].includes(label) ? c.transaction.amount : 0);
}, 0);
return [{json: {merchant_id: state.merchant_id, as_of: state.as_of,
  candidates: candidates.filter(c =>
    !open.some(q => q.txn_id === c.txn_id)),
  projected_turnover: aggregate, threshold: merchant.supply_kind === 'services' ? 2000000 : 4000000,
  already_asked_today: open.filter(q => q.question_id.startsWith('Q-' + dateKey + '-')).length}}];
""")
    w.http("Select questions", "/skills/select-questions", "provenance", "={{ JSON.stringify($json) }}")
    w.code("Question messages", """
const state = $('Collect page').last().json;
const merchant = $('Merchant').first().json;
return $input.first().json.selected.map(q => {
  const t = state.credits.find(c => c.transaction.txn_id === q.txn_id)?.transaction;
  if (!t) throw new Error('Selected question is not in the credit snapshot');
  const amount = '₹' + t.amount.toLocaleString('en-IN');
  const kn = merchant.preferred_language.startsWith('kn');
  const question = kn ? `${amount} · ${t.counterparty_name}: ಈ ಪಾವತಿ ಯಾವುದಕ್ಕಾಗಿ?` : `${amount} from ${t.counterparty_name}: what was this payment for?`;
  const options = kn ? '1 ಮಾರಾಟ · 2 ಕುಟುಂಬ · 3 ನನ್ನದೇ ಹಣ · 4 ಖಚಿತವಿಲ್ಲ' : '1 sale · 2 family · 3 my own money · 4 not sure';
  return {json: {merchant_id: state.merchant_id, txn_id: q.txn_id,
    question_id: 'Q-' + new Date(state.as_of).toLocaleDateString('en-CA', {timeZone:'Asia/Kolkata'}) + '-' + q.txn_id,
    expires_at: q.expires_at, language: merchant.preferred_language,
    text: question + (state.channel === 'whatsapp' ? '\\n' + options : ''),
    channel: state.channel, to: state.to, sim_at: state.as_of}};
});
""")
    w.node("Each question", "splitInBatches", {"batchSize": 1, "options": {}}, 3)
    w.node("Ask via WF30", "executeWorkflow", {"source": "database", "workflowId": "hisaabWF30out001", "options": {"waitForSubWorkflow": True}}, 1)
    w.node("Done", "noOp")
    w.chain("Nightly webhook", "Run context", "Merchant", "Business time", "Credit window", "Page request", "Read credits", "Collect page", "More credits?")
    w.link("02:00 IST", "Run context")
    w.link("More credits?", "Page request")
    w.link("More credits?", "Unlabelled credits", 1)
    w.chain("Unlabelled credits", "Each credit")
    w.link("Each credit", "Strictly prior history", 1)
    w.chain("Strictly prior history", "Classification input", "Classify rules", "Rule result", "Rule settled?")
    w.link("Rule settled?", "Rule proposal")
    w.link("Rule settled?", "Hard-case request", 1)
    w.chain("Hard-case request", "Sarvam hard case (local fake)", "Validate agent proposal", "Persist proposal")
    w.chain("Rule proposal", "Persist proposal", "Question candidate", "Each credit")
    w.chain("Each credit", "Classification complete", "Open questions", "Selection request", "Select questions", "Question messages", "Each question")
    w.link("Each question", "Ask via WF30", 1)
    w.link("Ask via WF30", "Each question")
    w.link("Each question", "Done")
    w.save("wf10-nightly-provenance.json")


def patch_channels():
    path = ROOT / "workflows" / "wf31-merchant-inbound.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    nodes = {n["name"]: n for n in data["nodes"]}
    # Keep Twilio verification. Both ingress paths meet at Normalise.
    w = Workflow(data["id"], data["name"])
    w.data = data
    if "App inbound" not in nodes:
        w.webhook("App inbound", "hisaab/wf31-assistant")
        w.code("App envelope", """
const body = $input.first().json.body;
if (!body || body.content_type !== 'text' || typeof body.text !== 'string' || !body.merchant_id || !body.sim_at) throw new Error('Invalid assistant envelope');
return [{json: {app: body}}];
""")
        w.chain("App inbound", "App envelope", "Normalise")
    nodes = {n["name"]: n for n in data["nodes"]}
    nodes["Normalise"]["parameters"]["jsCode"] = """
const item = $input.first().json, app = item.app;
const params = item.params || {};
const phones = {'whatsapp:+919999999999': 'MID_DEMO_SAHANA'};
const merchant_id = app ? app.merchant_id : phones[params.From];
if (!merchant_id) throw new Error('Unknown WhatsApp sender');
const text = (app ? app.text : params.Body || '').trim();
const words = {'1':'sale','2':'family','3':'own_money','4':'not_sure',
  'sale':'sale','family':'family','own_money':'own_money','own money':'own_money','my own money':'own_money',
  'loan_or_gift':'loan_or_gift','loan':'loan_or_gift','gift':'loan_or_gift','not_sure':'not_sure','not sure':'not_sure',
  'ಮಾರಾಟ':'sale','ಕುಟುಂಬ':'family','ನನ್ನದೇ ಹಣ':'own_money','ಖಚಿತವಿಲ್ಲ':'not_sure',
  'बिक्री':'sale','परिवार':'family','मेरा अपना पैसा':'own_money','पक्का नहीं':'not_sure'};
// App taps carry explicit question identity in text, within the frozen inbound contract.
// Never treat a delayed tap as an answer to whichever question is now oldest.
let tap = null;
if (app && text.startsWith('{')) {
  try { tap = JSON.parse(text); } catch { throw new Error('Malformed app tap'); }
  if (tap.type !== 'question_answer' || !tap.question_id || !tap.txn_id || !words[tap.answer]) throw new Error('Invalid app tap');
}
const answer = tap ? words[tap.answer] : words[text.toLowerCase()] || null;
return [{json: {core:'http://core:8000', fakes:'http://fakes:8200', merchant_id,
  from:params.From || null, text:tap ? tap.answer : text, answer,
  route:answer ? 'answer':'intent', channel:app ? 'app':'whatsapp',
  question_id:tap?.question_id || null, txn_id:tap?.txn_id || null,
  message_id:app?.message_id || params.MessageSid || null,
  language:app?.language || 'kn-IN', sim_at:app?.sim_at || null}}];
"""
    nodes["Build claim"]["parameters"]["jsCode"] = """
const inbound = $('Normalise').first().json;
const questions = $input.first().json.items || [];
const question = inbound.question_id ? questions.find(q => q.question_id === inbound.question_id && q.txn_id === inbound.txn_id) : questions[0];
if (!question) throw new Error('Question is no longer open; refresh before answering');
const home = $('Merchant clock').first().json;
return [{json: {...inbound, question_id:question.question_id, txn_id:question.txn_id,
  sim_at:inbound.sim_at || home.as_of, claim: {merchant_id:inbound.merchant_id,
    txn_id:question.txn_id, action:'answered', sim_at:inbound.sim_at || home.as_of,
    claim:{question_id:question.question_id, answer:inbound.answer,
      raw_text:inbound.text, language:question.language || inbound.language}}}}];
"""
    if "Merchant clock" not in nodes:
        w.http("Merchant clock", "/app/home", "app", query={"merchant": "={{ $json.merchant_id }}"})
    # Resolve simulation time on both inbound paths before branching.
    if "Inbound clock" not in nodes:
        w.code("Inbound clock", "return [{json: {...$('Normalise').first().json, sim_at: $('Normalise').first().json.sim_at || $input.first().json.as_of}}];")
    for source, dest in [("Normalise", "Merchant clock"), ("Merchant clock", "Inbound clock"),
                         ("Inbound clock", "A one-tap answer?")]:
        w.data["connections"][source] = {"main": [[{"node": dest, "type": "main", "index": 0}]]}
    w.data["connections"]["A one-tap answer?"]["main"][0] = [{"node": "Open questions", "type": "main", "index": 0}]
    nodes["Open questions"]["parameters"]["url"] = "http://core:8000/app/questions"
    nodes["Open questions"]["parameters"]["queryParameters"]["parameters"][0]["value"] = "={{ $('Normalise').first().json.merchant_id }}"
    nodes["Acknowledge"]["parameters"]["jsCode"] = """
const inbound = $('Build claim').first().json;
return [{json: {merchant_id:inbound.merchant_id,
  text:inbound.language.startsWith('kn') ? 'ನಿಮ್ಮ ಉತ್ತರ ದಾಖಲಾಗಿದೆ.' : 'Your answer has been recorded.',
  language:inbound.language, channel:inbound.channel, to:inbound.from,
  conversation_id:'wf31-' + inbound.merchant_id, in_reply_to:inbound.message_id,
  sim_at:inbound.sim_at}}];
"""
    nodes["Reply to free text"]["parameters"]["jsCode"] = """
const inbound = $('Inbound clock').first().json;
const raw = JSON.stringify($input.first().json || {}).toLowerCase();
const text = raw.includes('hide_income') ? "I can't help hide income. I can help you keep accurate records." : 'Reply 1 sale · 2 family · 3 my own money · 4 not sure';
return [{json: {merchant_id:inbound.merchant_id, text, language:inbound.language,
  channel:inbound.channel, to:inbound.from, conversation_id:'wf31-' + inbound.merchant_id,
  sim_at:inbound.sim_at}}];
"""
    w.save(path.name)
    path = ROOT / "workflows" / "wf30-merchant-outbound.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    nodes = {n["name"]: n for n in data["nodes"]}
    # App sends do not consume the sandbox's three-second allowance.
    data["connections"]["Prepare message"]["main"][0][0]["node"] = "WhatsApp or app?"
    data["connections"]["WhatsApp or app?"]["main"][0][0]["node"] = "Wait 3s (sandbox rate limit)"
    data["connections"]["Wait 3s (sandbox rate limit)"]["main"][0][0]["node"] = "Send on WhatsApp"
    code = nodes["Prepare message"]["parameters"]["jsCode"]
    if "WhatsApp needs a joined recipient" not in code:
        code = code.replace("if (!input.text) throw", "if (input.channel === 'whatsapp' && !input.to) throw new Error('WhatsApp needs a joined recipient');\n  if (!input.text) throw")
    nodes["Prepare message"]["parameters"]["jsCode"] = code
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def wf20():
    # The frozen API has no endpoint to register a resume URL. Poll the officer read model;
    # approval and the outbox gate stay in core. Never trust a webhook body's approval bit.
    w = Workflow("hisaabWF20mvp001", "hisaab/WF20 freeze-response")
    w.webhook("Freeze opened", "hisaab/wf20-freeze")
    w.code("Freeze context", """
const b = $input.first().json.body;
if (!b?.case_id || !b.merchant_id || !b.opened_at) throw new Error('case.opened needs case_id, merchant_id, opened_at');
return [{json: {...b, max_polls: 120}}];
""")
    w.http("Build evidence pack", "/packs", "evidence", "={{ JSON.stringify({merchant_id:$json.merchant_id, case_id:$json.case_id, pack_type:'freeze', sim_at:$json.opened_at}) }}")
    w.code("Poll budget", """
let previous;
try { previous = $('Check decision').item.json; } catch { previous = {poll_count: 0}; }
return [{json: {poll_count: previous.poll_count + 1}}];
""")
    w.node("Wait for officer", "wait", {"amount": 5, "unit": "seconds"}, 1.1,
           webhookId=str(uuid.uuid5(uuid.NAMESPACE_URL, "wf20-wait")))
    w.http("Officer decision", "={{ 'http://core:8000/app/officer/cases/' + encodeURIComponent($('Freeze context').first().json.case_id) }}", "officer")
    w.code("Check decision", """
const view = $input.first().json;
const built = $('Build evidence pack').first().json;
if (view.case.case_id !== built.case_id || view.pack_id !== built.pack_id) throw new Error('Officer decision is for a different case or pack');
return [{json: {...view, poll_count: $('Poll budget').item.json.poll_count, approved:view.status === 'approved',
  terminal:['sent','rejected','escalated'].includes(view.status)}}];
""")
    w.test("Approved?", "={{ String($json.approved) }}")
    w.test("Terminal decision?", "={{ String($json.terminal) }}")
    w.test("Polls remaining?", "={{ String($json.poll_count < $('Freeze context').first().json.max_polls) }}")
    w.code("Approval wait expired", """
throw new Error('Officer approval wait expired after 120 polls. The pack remains awaiting approval; retry this case webhook after review. Nothing was sent.');
""")
    w.http("Merchant simulation clock", "/app/home", "app", query={"merchant": "={{ $('Freeze context').first().json.merchant_id }}"})
    w.http("Simulated send (core gate)", "={{ 'http://core:8000/outbox/' + encodeURIComponent($('Build evidence pack').first().json.pack_id) + '/send' }}",
           "officer", "={{ JSON.stringify({destination:'bank-nodal-and-ncrp', sim_at:$json.as_of}) }}")
    w.code("Send status", """
const sent = $input.first().json;
if (!sent.sent || sent.simulated !== true) throw new Error('Expected a simulated outbox delivery');
return [{json:{merchant_id:$('Freeze context').first().json.merchant_id,
  channel:'app', language:'en-IN', text:'Your evidence pack was approved and sent in the simulation.',
  sim_at:sent.ledger_entry.sim_at}}];
""")
    w.node("Notify via WF30", "executeWorkflow", {"source": "database", "workflowId": "hisaabWF30out001", "options": {}}, 1)
    w.node("Done", "noOp")
    w.chain("Freeze opened", "Freeze context", "Build evidence pack", "Poll budget", "Wait for officer", "Officer decision", "Check decision", "Approved?")
    w.chain("Approved?", "Merchant simulation clock", "Simulated send (core gate)", "Send status", "Notify via WF30", "Done")
    w.link("Approved?", "Terminal decision?", 1)
    w.link("Terminal decision?", "Done")
    w.link("Terminal decision?", "Polls remaining?", 1)
    w.link("Polls remaining?", "Poll budget")
    w.link("Polls remaining?", "Approval wait expired", 1)
    w.save("wf20-freeze-response.json")


if __name__ == "__main__":
    credentials_path = ROOT / "credentials" / "local.json"
    credentials = json.loads(credentials_path.read_text(encoding="utf-8"))
    for credential in credentials:
        if credential["id"] == ROLES["sarvam"][0]:
            credential["data"] = {"name": "Authorization", "value": "Bearer ${SARVAM_API_KEY}"}
    if not any(c["id"] == ROLES["webhook"][0] for c in credentials):
        credentials.append({"id": ROLES["webhook"][0], "name": ROLES["webhook"][1],
                            "type": "httpHeaderAuth", "data": {
                                "name": "X-N8N-Webhook-Secret", "value": "${N8N_WEBHOOK_SECRET}"}})
    credentials_path.write_text(json.dumps(credentials, indent=2) + "\n", encoding="utf-8")
    wf10()
    patch_channels()
    wf20()
