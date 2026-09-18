"""Joint first-gate check against REAL core/local n8n/fakes, once A's H6 lands.

Requires visible demo data loaded through 10 Mar 02:00 and unclassified 8–9 Mar credits.
Does not seed/reset data or spend credits. --restart-core also verifies restart persistence.
"""
from datetime import datetime
from pathlib import Path
import argparse
import importlib.util
import json
import os
import subprocess
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("n8n_cli", ROOT / "n8n/cli.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--merchant', default='MID_DEMO_SAHANA')
    parser.add_argument('--restart-core', action='store_true')
    parser.add_argument('--browser', action='store_true', help='Two real M2 taps, then one signed WhatsApp reply')
    parser.add_argument('--timeout', type=int, default=1800, metavar='SECONDS',
        help='Seconds to wait for WF10 and for persistence (default 1800). WF10 took 112 s on a '
             '16 GiB machine and over 1200 s on a smaller one. Interrupting it leaves the window '
             'part-labelled, and WF10 skips labelled credits, so that database cannot select three '
             'questions again without tasks.py reset.')
    args = parser.parse_args()
    env = cli.load_env()
    if env.get('HISAAB_LIVE', '0') != '0':
        raise SystemExit('Run this checkpoint with HISAAB_LIVE=0 and local n8n/fakes')

    def request(path, role='app', body=None, workflow=False):
        base = 'http://localhost:5678/webhook' if workflow else 'http://localhost:8080/api'
        headers = {'Content-Type': 'application/json'}
        if workflow:
            headers['X-N8N-Webhook-Secret'] = env.get('N8N_WEBHOOK_SECRET', 'dev-webhook-secret')
        else:
            headers['X-Hisaab-Key'] = env.get('KEY_' + role.upper(), 'dev-' + role)
        r = urllib.request.Request(base + path, headers=headers,
            data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(r, timeout=15) as response:
            raw = response.read()
            return json.loads(raw) if raw else {}

    def wait(predicate, description):
        for attempt in range(args.timeout):
            value = predicate()
            if value:
                return value
            if attempt % 15 == 0:
                print('Waiting for ' + description, flush=True)
            time.sleep(1)
        raise AssertionError('Timed out waiting for ' + description)

    def wf10_execution():
        # Status and duration of the newest WF10 run, read from the local n8n database.
        # No SQL string literals here, so the row is filtered in Python instead of quoted inline.
        sql = ('select "workflowId", status, '
               'round(extract(epoch from ("stoppedAt" - "startedAt"))::numeric, 1) '
               'from execution_entity order by id desc limit 20')
        result = subprocess.run(['docker', 'compose', 'exec', '-T', 'db', 'psql', '-U',
                                 env.get('POSTGRES_USER', 'hisaab'), '-d', 'n8n-local', '-tAc', sql],
                                cwd=ROOT, capture_output=True, text=True,
                                encoding='utf-8', errors='replace')
        for row in (result.stdout or '').splitlines():
            parts = row.split('|')
            if len(parts) == 3 and parts[0] == 'hisaabWF10mvp001':
                return parts[1], parts[2]
        return 'unknown', '?'

    m = urllib.parse.quote(args.merchant, safe='')
    home = request('/app/home?merchant=' + m)
    if home['merchant_id'] != args.merchant:
        raise SystemExit('PENDING H6: /app/home still returns another merchant fixture')
    if home['as_of'][:10] != '2026-03-10' and home['as_of'][:10] != '2026-03-09':
        raise SystemExit('Load the demo through 10 Mar 02:00 IST before running CP1')
    outbox_url = 'http://localhost:8200/twilio/outbox'
    before_outbox = urllib.request.urlopen(outbox_url).read().decode()
    resumed = len(request('/app/questions?merchant=' + m)['items']) == 3
    request('/hisaab/wf10-nightly', body={'merchant_id': args.merchant, 'as_of': home['as_of'], 'mode': 'live',
        'channel': 'whatsapp', 'to': 'whatsapp:+919999999999',
        'window_from': '2026-03-08', 'window_to': '2026-03-10'}, workflow=True)
    questions = wait(lambda: (q if len((q := request('/app/questions?merchant=' + m))['items']) == 3 else None), 'the three demo questions')
    # A resumed run can find three questions an earlier invocation left behind, so the gate has to
    # look at WF10 itself: a run that died still ends with the questions sitting there, and without
    # this the checkpoint reports PASS over a broken workflow.
    status, seconds = wf10_execution()
    assert status == 'success', f'WF10 execution ended {status} after {seconds}s, not success'
    print(f'WF10 execution: {status} in {seconds}s', flush=True)
    answers = {15000: 'own_money', 7500: 'family', 4850: 'sale'}
    assert {q['amount'] for q in questions['items']} == set(answers), questions
    ids = {q['question_id'] for q in questions['items']}
    assert all(q['language'].startswith('kn') for q in questions['items'])
    outbox = urllib.request.urlopen(outbox_url).read().decode()
    for q in questions['items']:
        assert q['question'] in outbox, 'question missing from the WhatsApp outbox'
        assert resumed or q['question'] not in before_outbox, 'question was not newly sent'
    print('PASS: three%s Kannada questions in fake WhatsApp outbox and real M2 read model'
          % ('' if resumed else ' new'), flush=True)
    if resumed:
        print('  (resumed run: the questions already existed, so novelty was not re-checked)', flush=True)

    def entries():
        result, cursor = [], None
        while True:
            path = '/ledger/' + m + '/entries?limit=200' + ('&cursor=' + urllib.parse.quote(cursor, safe='') if cursor else '')
            page = request(path, 'officer')
            result.extend(page['entries'])
            cursor = page.get('next_cursor')
            if not cursor:
                return result

    initial = entries()
    machine = {e['txn_id']: e['payload'] for e in initial if e['kind'] == 'label.proposed'}
    assert machine, 'Proposals must exist in the real chain'
    as_of = datetime.fromisoformat(home['as_of'])
    labelled = [e for e in initial if e['kind'] == 'label.proposed'
                and datetime.fromisoformat(e['sim_at'].replace('Z', '+00:00')) == as_of]
    assert len(labelled) == 68, f'Expected 68 proposals in this window, got {len(labelled)}'
    browser_errors = []
    if args.browser:
        web = ROOT / 'services/web'
        sys_path = __import__('sys').path
        sys_path.insert(0, str(web / '.browser-check'))
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(executable_path=os.environ.get('HISAAB_BROWSER_EXECUTABLE'))
            context = browser.new_context(viewport={'width': 360, 'height': 820}, service_workers='block')
            page = context.new_page()
            page.on('pageerror', lambda error: browser_errors.append(str(error)))
            page.route('**/*', lambda route: route.continue_() if route.request.url.startswith('http://localhost:8080') else route.abort())
            page.goto('http://localhost:8080/')
            page.get_by_text('Sahana Stores', exact=True).wait_for()
            page.get_by_text('3 payments to confirm', exact=True).first.wait_for()
            result_dir = web / 'test-results'
            result_dir.mkdir(exist_ok=True)
            page.screenshot(path=str(result_dir / 'cp1-real-home-360.png'), full_page=True)
            page.get_by_role('button', name='Confirm payments', exact=True).click()
            page.screenshot(path=str(result_dir / 'cp1-real-confirm-360.png'), full_page=True)
            for index in range(2):
                current = request('/app/questions?merchant=' + m)['items'][0]
                answer = answers[current['amount']]
                title = next(c['text'] for c in current['answer_chips'] if c['answer'] == answer)
                page.get_by_text(current['payer_name'], exact=True).wait_for()
                page.get_by_role('button', name=title, exact=True).click()
                page.get_by_role('button', name='Save answer', exact=True).click()
                wait(lambda: all(q['question_id'] != current['question_id'] for q in request('/app/questions?merchant=' + m)['items']), 'M2 answer ' + str(index + 1))
            # One numbered reply exercises the signed WhatsApp route. Voice is deferred.
            last = request('/app/questions?merchant=' + m)['items'][0]
            digit = {'sale':'1', 'family':'2', 'own_money':'3'}[answers[last['amount']]]
            subprocess.run([__import__('sys').executable, 'tasks.py', 'fake-wa', digit], cwd=ROOT, check=True)
            page.get_by_text('All caught up', exact=True).wait_for(timeout=30000)
            assert page.locator('body').evaluate('(b) => b.scrollWidth <= innerWidth')
            page.screenshot(path=str(result_dir / 'cp1-real-complete-360.png'), full_page=True)
            assert not browser_errors, browser_errors
            browser.close()
        print('PASS: two real M2 taps and one signed WhatsApp reply close the three questions', flush=True)
    else:
        for q in questions['items']:
            answer = answers[q['amount']]
            response = request('/assistant/inbound', body={'merchant_id': args.merchant,
                'message_id': 'cp1-' + q['question_id'], 'content_type': 'text',
                'text': json.dumps({'type': 'question_answer', 'question_id': q['question_id'], 'txn_id': q['txn_id'], 'answer': answer}),
                'language': q['language'], 'sim_at': home['as_of']})
            assert response['accepted'] and response['forwarded_to_workflow']
    wait(lambda: not request('/app/questions?merchant=' + m)['items'], 'persisted answers')
    if args.restart_core:
        subprocess.run(['docker', 'compose', 'restart', 'core'], cwd=ROOT, check=True)
        time.sleep(5)
    final = entries()
    claims = [e for e in final if e['kind'] == 'claim.answered' and e['payload']['question_id'] in ids]
    assert len(claims) == 3 and all('label' not in c['payload'] for c in claims)
    assert {e['txn_id']: e['payload'] for e in final if e['kind'] == 'label.proposed'} == machine
    assert request('/ledger/verify?merchant=' + m, 'officer')['ok']
    assert not request('/app/questions?merchant=' + m)['items']
    print('PASS CP1: real proposals → three questions → WF31 answers → unchanged machine proposals → verified chain' + (' → restart persistence' if args.restart_core else ''), flush=True)


if __name__ == '__main__':
    main()
