"""Real local CP2: rails lien -> WF20 -> evidence -> O2 approval -> simulated send -> M5.

--prepare snapshots the current demo, replays to just before the visible lien, then posts it
through the rails endpoint so the detector starts WF20 after commit. No automatic reset.
Requires published B workflows, the visible demo mount, Playwright and Chromium.
"""
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse, quote
import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / 'services/web'
spec = importlib.util.spec_from_file_location('n8n_cli', ROOT / 'n8n/cli.py')
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--timeout', type=int, default=300)
    args = parser.parse_args()
    env = cli.load_env()
    if env.get('HISAAB_LIVE', '0') != '0':
        raise SystemExit('CP2 requires HISAAB_LIVE=0 and local n8n/core/fakes')

    def request(path, role='app', body=None, raw=False, workflow=False):
        base = 'http://localhost:5678/webhook' if workflow else 'http://localhost:8080/api'
        headers = {'Content-Type': 'application/json'}
        headers.update({'X-N8N-Webhook-Secret': env.get('N8N_WEBHOOK_SECRET', 'dev-webhook-secret')}
                       if workflow else {'X-Hisaab-Key': env.get('KEY_' + role.upper(), 'dev-' + role)})
        req = urllib.request.Request(base + path, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        with urllib.request.urlopen(req, timeout=60) as response:
            data = response.read()
            return data if raw else json.loads(data) if data else {}

    def wait(predicate, description):
        end = time.monotonic() + args.timeout
        last_update = 0
        while time.monotonic() < end:
            value = predicate()
            if value:
                return value
            if time.monotonic() - last_update > 20:
                print('Waiting for ' + description, flush=True)
                last_update = time.monotonic()
            time.sleep(2)
        raise AssertionError('Timed out waiting for ' + description)

    def execution():
        sql = ('SELECT id, status FROM execution_entity '
               "WHERE \"workflowId\" = 'hisaabWF20mvp001' ORDER BY id DESC LIMIT 1")
        result = subprocess.run(['docker', 'compose', 'exec', '-T', 'db', 'psql', '-U',
            env.get('POSTGRES_USER', 'hisaab'), '-d', 'n8n-local', '-tAc', sql],
            cwd=ROOT, check=True, capture_output=True, text=True)
        return result.stdout.strip().split('|')

    previous_run = execution()[0] if args.prepare else None

    def completed_run():
        run = execution()
        if len(run) != 2 or run[0] == previous_run:
            return None
        assert run[1] not in ('error', 'crashed', 'canceled'), 'WF20 ended ' + run[1]
        return run if run[1] == 'success' else None

    config = request('/config')
    assert config['live'] is False
    events = json.loads((ROOT / 'data/demo/visible/rails_events.json').read_text(encoding='utf-8'))
    lien = next(e for e in events if e['type'] == 'lien_marked' and e['merchant_id'] == 'MID_DEMO_SAHANA')
    merchant = lien['merchant_id']
    case_id = 'CASE-FREEZE-' + lien['event_id']
    detail_path = '/app/officer/cases/' + quote(case_id, safe='')
    home_path = '/app/home?merchant=' + quote(merchant, safe='')
    cases_path = '/app/cases?merchant=' + quote(merchant, safe='')

    if args.prepare:
        before_lien = datetime.fromisoformat(lien['ts']) - timedelta(seconds=1)
        assert datetime.fromisoformat(request(home_path)['as_of']) <= before_lien, 'Restore cp2-before-freeze before preparing another run'
        assert not any(c['case_id'] == case_id for c in request(cases_path)['items']), 'Freeze case already exists; reset before a cold CP2'
        subprocess.run([sys.executable, 'tasks.py', 'snapshot', '--name', 'cp2-before-freeze'], cwd=ROOT, check=True)
        subprocess.run([sys.executable, 'tasks.py', 'replay', '--split', 'demo', '--until', before_lien.isoformat()], cwd=ROOT, check=True)
        request('/sim/clock', 'admin', {'sim_at': lien['ts']})
        result = request('/rails/events', 'rails', {'events': [lien], 'sim_at': lien['ts']})
        assert result == {'accepted': 1, 'opened_case_ids': [case_id]}, result
        print('PASS: real lien opens its case and starts WF20 through the after-commit hook', flush=True)

    def built_pack():
        try:
            view = request(detail_path, 'officer')
            return view if view['pack_id'] else None
        except urllib.error.HTTPError as error:
            if error.code != 404:
                raise
            return None
    detail = wait(built_pack, 'WF20 to build the real evidence pack')
    assert detail['status'] == 'awaiting_approval', detail['status']
    assert detail['chain_ok'] is True
    pack_id = detail['pack_id']
    pack_path = '/packs/' + quote(pack_id, safe='')
    evidence = request(pack_path + '.json', 'officer')
    assert (evidence['pack_id'], evidence['case_id'], evidence['merchant_id']) == (pack_id, case_id, merchant)
    isolated = evidence['isolation']
    matched = isolated['matched']
    assert matched['txn_id'] == 'DM0038619' and matched['utr'] == lien['disputed_utr']
    assert matched['amount'] == 4200 and datetime.fromisoformat(matched['ts']).date().isoformat() == '2026-03-21'
    assert set(isolated['found_by']) == {'utr', 'amount_date'}
    assert isolated['seven_day_credit_count'] == 339
    assert len(isolated['same_amount_candidates']) == 1
    decoy = isolated['same_amount_candidates'][0]
    assert decoy['txn_id'] != matched['txn_id'] and decoy['amount'] == 4200
    assert datetime.fromisoformat(decoy['ts']).date().isoformat() == '2026-03-18'
    assert isolated['bill']['total'] == 4200 and isolated['bill']['line_items']
    assert isolated['device']['terminal_id'] == 'POS01'
    assert evidence['tier_totals']['1'] == {'amount': 4200, 'count': 1}
    build = request('/packs', 'evidence', {'merchant_id': merchant, 'case_id': case_id, 'pack_type': 'freeze', 'sim_at': lien['ts']})
    assert build['pack_id'] == pack_id, 'An identical build created another pack'
    pdf = request(pack_path + '.pdf', 'officer', raw=True)
    assert pdf.startswith(b'%PDF-') and len(pdf) > 1000
    assert hashlib.sha256(pdf).hexdigest() == build['pdf_sha256']
    print('PASS: both isolation badges, excluded decoy, 1 of 339, real bill/device, Tier 1 and hashed PDF', flush=True)

    try:
        request('/outbox/' + quote(pack_id, safe='') + '/send', 'officer', {'destination': 'bank-nodal-and-ncrp', 'sim_at': request(home_path)['as_of']})
        raise AssertionError('An unapproved pack was sent')
    except urllib.error.HTTPError as error:
        assert error.code == 409
    outbox = request('/app/officer/outbox', 'officer')
    assert not any(row['pack_id'] == pack_id for row in outbox['items'])
    print('PASS: awaiting approval produces no delivery; core refuses an early send', flush=True)

    if args.prepare:
        # These declines follow the visible lien. They must not be invented as its prior burst.
        declines = [e for e in events if e['type'] == 'payment_declined' and e['merchant_id'] == merchant and e['ts'].startswith('2026-03-24')]
        assert len(declines) == 3
        sim_at = max(e['ts'] for e in declines)
        request('/sim/clock', 'admin', {'sim_at': sim_at})
        result = request('/rails/events', 'rails', {'events': declines, 'sim_at': sim_at})
        assert result == {'accepted': 3, 'opened_case_ids': []}, result

    sys.path.insert(0, str(WEB / '.browser-check'))
    from playwright.sync_api import sync_playwright
    results = WEB / 'test-results'
    results.mkdir(exist_ok=True)
    errors, external = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=os.environ.get('HISAAB_BROWSER_EXECUTABLE'))
        for width in (360, 412):
            context = browser.new_context(viewport={'width': width, 'height': 820}, service_workers='block', accept_downloads=True)
            context.add_init_script('sessionStorage.setItem("hisaab-officer-key", ' + json.dumps(env.get('KEY_OFFICER', 'dev-officer')) + ')')
            def route(handler):
                if urlparse(handler.request.url).netloc != 'localhost:8080':
                    external.append(handler.request.url)
                    handler.abort()
                else:
                    handler.continue_()
            context.route('**/*', route)
            officer, tracker = context.new_page(), context.new_page()
            for page in (officer, tracker):
                page.set_default_timeout(args.timeout * 1000)
                page.on('pageerror', lambda error: errors.append(str(error)))
            tracker.goto('http://localhost:8080/cases?merchant=' + merchant)
            if width == 360:
                tracker.get_by_text('awaiting approval', exact=True).wait_for()
                assert tracker.get_by_role('list', name='Case progress').locator('[aria-current="step"]').inner_text().endswith('Evidence pack built')
                tracker.screenshot(path=str(results / 'cp2-awaiting-360.png'), full_page=True)
                officer.goto('http://localhost:8080/officer')
                officer.get_by_text(case_id, exact=True).wait_for()
                officer.get_by_role('button', name='Review case', exact=True).click()
            else:
                officer.goto('http://localhost:8080/officer/cases/' + case_id)
            officer.get_by_text('UTR match', exact=True).wait_for()
            officer.get_by_text('Amount + date match', exact=True).wait_for()
            officer.get_by_text('1 selected from 339 credits in seven days.', exact=True).wait_for()
            officer.get_by_text('Same-amount payments · not selected', exact=True).wait_for()
            assert officer.get_by_text('18 Mar 2026', exact=False).is_visible()
            assert officer.get_by_text('21 Mar 2026', exact=False).is_visible()
            assert officer.locator('body').evaluate('(b) => b.scrollWidth <= innerWidth')
            officer.screenshot(path=str(results / f'cp2-officer-{width}.png'), full_page=True)
            with officer.expect_download() as pending_download:
                officer.get_by_role('button', name='Download evidence PDF →', exact=True).click()
            downloaded = pending_download.value
            assert hashlib.sha256(Path(downloaded.path()).read_bytes()).hexdigest() == build['pdf_sha256']
            if width == 360:
                officer.get_by_label('Officer reference').fill('CP2-OFFICER')
                officer.get_by_label('Review note / rejection reason').fill('Checked both matches, excluded decoy, bill and device evidence.')
                officer.get_by_role('button', name='Approve and send (simulated)', exact=True).click()
            tracker.get_by_text('sent', exact=True).wait_for()
            assert tracker.get_by_role('list', name='Case progress').locator('[aria-current="step"]').count() == 0
            assert tracker.get_by_text('Evidence delivery is simulated. The bank decides whether to change the hold.', exact=True).is_visible()
            assert tracker.locator('body').evaluate('(b) => b.scrollWidth <= innerWidth')
            tracker.screenshot(path=str(results / f'cp2-sent-{width}.png'), full_page=True)
            context.close()
            print(f'PASS {width}px: real officer evidence/PDF and merchant tracker; ' + ('O2 approval -> WF20 simulated send' if width == 360 else 'sent state survives a new browser session'), flush=True)
        browser.close()
    assert not errors and not external, (errors, external)
    sent = request('/app/officer/outbox', 'officer')['items']
    deliveries = [row for row in sent if row['pack_id'] == pack_id]
    assert len(deliveries) == 1 and deliveries[0]['simulated'] is True
    assert request(detail_path, 'officer')['status'] == 'sent'
    assert request('/ledger/verify?merchant=' + quote(merchant, safe=''), 'officer')['ok'] is True
    wait(completed_run, 'the original WF20 execution to finish successfully')
    previous_run = execution()[0]
    request('/hisaab/wf20-freeze', workflow=True, body={'case_id': case_id, 'merchant_id': merchant, 'opened_at': lien['ts']})
    wait(completed_run, 'the sent-case WF20 retry to finish successfully')
    assert len([row for row in request('/app/officer/outbox', 'officer')['items'] if row['pack_id'] == pack_id]) == 1
    print('PASS: one simulated outbox delivery, verified chain, sent-case webhook retry creates no second delivery', flush=True)
    print('CP2 prototype freeze loop passed. Full CP2 voice/notice/grievance checks remain deferred.', flush=True)


if __name__ == '__main__':
    main()
