"""Joint first-gate check against REAL core/local n8n/fakes, once A's H6 lands.

Requires visible demo data loaded through 10 Mar 02:00 and unclassified 8–9 Mar credits.
Does not seed/reset data or spend credits. --restart-core also verifies restart persistence.
"""
from pathlib import Path
import argparse
import importlib.util
import json
import subprocess
import time
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("n8n_cli", ROOT / "n8n/cli.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--merchant', default='MID_DEMO_BLR')
    parser.add_argument('--restart-core', action='store_true')
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
        for attempt in range(90):
            value = predicate()
            if value:
                return value
            if attempt % 15 == 0:
                print('Waiting for ' + description, flush=True)
            time.sleep(1)
        raise AssertionError('Timed out waiting for ' + description)

    m = urllib.parse.quote(args.merchant, safe='')
    home = request('/app/home?merchant=' + m)
    if home['merchant_id'] != args.merchant:
        raise SystemExit('PENDING H6: /app/home still returns another merchant fixture')
    if home['as_of'][:10] != '2026-03-10' and home['as_of'][:10] != '2026-03-09':
        raise SystemExit('Load the demo through 10 Mar 02:00 IST before running CP1')
    request('/hisaab/wf10-nightly', body={'merchant_id': args.merchant, 'as_of': home['as_of'], 'mode': 'live', 'channel': 'app'}, workflow=True)
    questions = wait(lambda: (q if len((q := request('/app/questions?merchant=' + m))['items']) == 3 else None), 'the three demo questions')
    answers = {15000: 'own_money', 7500: 'family', 4850: 'sale'}
    assert {q['amount'] for q in questions['items']} == set(answers), questions
    ids = {q['question_id'] for q in questions['items']}

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
