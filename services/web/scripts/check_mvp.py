"""Browser checks for the two MVP surfaces, using wire-shaped stateful API doubles.

Requires playwright (a workspace-local install in .browser-check is supported) and Chromium.
Start the web service, then run python services/web/scripts/check_mvp.py.
"""
from pathlib import Path
from urllib.parse import urlparse
import copy
import json
import os
import sys

WEB = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WEB / ".browser-check"))
from playwright.sync_api import sync_playwright

ROOT = WEB.parents[1]
fixtures = json.loads((ROOT / "services/core/app/fixtures/app_screens.json").read_text(encoding="utf-8"))
results = WEB / "test-results"
results.mkdir(exist_ok=True)


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get('HISAAB_BROWSER_EXECUTABLE'))
        for width in (360, 412):
            state = copy.deepcopy(fixtures)
            answers, decisions, pdf_headers, errors = [], [], [], []
            persist = {"enabled": False, "remove": None}
            officer = state['GET /app/officer/cases/{id}']
            isolation = json.loads((ROOT / 'services/core/app/fixtures/skills.json').read_text(encoding='utf-8'))['POST /skills/isolate']
            pack = {'pack_id': officer['pack_id'], 'case_id': officer['case']['case_id'],
                    'merchant_id': officer['case']['merchant_id'], 'isolation': isolation}
            context = browser.new_context(viewport={"width": width, "height": 820}, service_workers="block")
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))

            def route(handler):
                request = handler.request
                path = urlparse(request.url).path
                if not request.url.startswith("http://localhost:8080"):
                    handler.abort(); return
                if not path.startswith("/api/"):
                    handler.continue_(); return
                assert request.headers.get("x-hisaab-key") == ("dev-officer" if '/officer/' in path or '/packs/' in path else "dev-app")
                if path == "/api/assistant/inbound":
                    body = request.post_data_json
                    answers.append(body)
                    tap = json.loads(body["text"])
                    assert tap["type"] == "question_answer" and "label" not in tap
                    if persist["enabled"]:
                        persist["remove"] = tap["question_id"]
                    data = {"accepted": True, "conversation_id": "test", "forwarded_to_workflow": persist["enabled"]}
                elif path.startswith("/api/packs/") and path.endswith("/approve"):
                    decisions.append(request.post_data_json)
                    state["GET /app/officer/cases/{id}"]["status"] = "approved"
                    data = {"status": "approved", "workflow_resumed": True}
                elif path.endswith(".pdf"):
                    pdf_headers.append(request.headers)
                    handler.fulfill(status=200, content_type="application/pdf", body=b"%PDF-1.4\n%%EOF"); return
                elif path.startswith('/api/packs/') and path.endswith('.json'):
                    data = pack
                else:
                    key = 'GET ' + path.removeprefix('/api')
                    if path.startswith('/api/app/officer/cases/'):
                        key = 'GET /app/officer/cases/{id}'
                    if key == 'GET /app/questions' and persist['remove']:
                        state[key]['items'] = [q for q in state[key]['items'] if q['question_id'] != persist['remove']]
                        persist['remove'] = None
                    data = state.get(key)
                    if data is None:
                        handler.fulfill(status=404, json={"detail": "Unknown test route"}); return
                handler.fulfill(status=200, json=data)

            page.route("**/*", route)
            page.goto('http://localhost:8080/')
            page.get_by_text('Sahana Stores', exact=True).wait_for()
            assert page.locator('body').evaluate('(b) => b.scrollWidth <= innerWidth')
            page.screenshot(path=str(results / f'home-{width}.png'), full_page=True)
            page.get_by_role('button', name='Confirm payments', exact=True).click()
            page.get_by_text('ANITHA R', exact=True).wait_for()
            save = page.get_by_role('button', name='Save answer', exact=True)
            assert save.is_disabled()
            page.get_by_role('button', name='ಕುಟುಂಬ', exact=True).click()
            save.click()
            page.get_by_role('alert').get_by_text('Your answer could not reach the workflow. Please retry.').wait_for()
            assert page.get_by_text('ANITHA R', exact=True).is_visible()
            persist['enabled'] = True
            page.screenshot(path=str(results / f'confirm-{width}.png'), full_page=True)
            save.click()
            page.get_by_text('MANJULA S', exact=True).wait_for()
            assert json.loads(answers[-1]['text'])['question_id'] == 'Q1'
            for payer in ('MANJULA S', 'RAHUL K'):
                page.get_by_text(payer, exact=True).wait_for()
                page.get_by_role('button', name='ಮಾರಾಟ', exact=True).click()
                page.get_by_role('button', name='Save answer', exact=True).click()
            page.get_by_text('All caught up', exact=True).wait_for()
            assert len(answers) == 4  # One failed forward and three successful answers.
            page.goto('http://localhost:8080/officer')
            page.get_by_role('button', name='Review case', exact=True).click()
            page.get_by_role('button', name='Download evidence PDF →', exact=True).wait_for()
            page.get_by_text('UTR match', exact=True).wait_for()
            page.get_by_text('Amount + date match', exact=True).wait_for()
            page.get_by_text('1 selected from 339 credits in seven days.', exact=True).wait_for()
            page.get_by_role('button', name='Download evidence PDF →', exact=True).click()
            page.wait_for_timeout(200)
            assert pdf_headers
            page.get_by_role('button', name='Reject', exact=True).click()
            page.get_by_text('Enter a reason before rejecting', exact=True).wait_for()
            assert not decisions
            page.screenshot(path=str(results / f'officer-{width}.png'), full_page=True)
            page.get_by_role('button', name='Approve and send (simulated)', exact=True).click()
            page.get_by_text('approved', exact=True).wait_for()
            assert decisions[0]['sim_at'] == state['GET /app/home']['as_of']
            state['GET /app/cases']['items'][0]['status'] = 'sent'
            page.goto('http://localhost:8080/cases')
            page.get_by_text('Sent to bank and police (simulated)', exact=True).wait_for()
            assert page.locator('body').evaluate('(b) => b.scrollWidth <= innerWidth')
            page.screenshot(path=str(results / f'cases-{width}.png'), full_page=True)
            assert not errors, errors
            print(f'PASS {width}px: home, answer failure/retry/persistence confirmation, all questions, officer PDF/approve/reject, case tracker')
            context.close()
        browser.close()


if __name__ == '__main__':
    main()
