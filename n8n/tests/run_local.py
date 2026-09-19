"""Exercise isolated copies of B workflows in local n8n, against mock_core on core:8300.

No live providers, real merchant data, or product workflow modifications.
Run python n8n/tests/run_local.py. It starts and stops its own isolated API double on :8300.
"""
from pathlib import Path
import json
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
NOW = '2026-03-10T02:00:00+05:30'


def docker(*args, capture=False):
    return subprocess.run(["docker", "compose", *args], cwd=ROOT, check=True,
                          capture_output=capture, text=True)


def mock(path="/test/state", body=None):
    code = "import urllib.request,json; r=urllib.request.Request('http://127.0.0.1:8300" + path + "',data="
    code += repr(json.dumps(body).encode()) if body is not None else "None"
    code += ",headers={'Content-Type':'application/json'}); print(urllib.request.urlopen(r).read().decode())"
    return json.loads(docker("exec", "-T", "core", ".venv/bin/python", "-c", code, capture=True).stdout)


def webhook(path, body, secret=True):
    request = urllib.request.Request("http://localhost:5678/webhook/test/" + path,
        data=json.dumps(body).encode(), headers={"Content-Type": "application/json",
        **({"X-N8N-Webhook-Secret": "dev-webhook-secret"} if secret else {})})
    return urllib.request.urlopen(request, timeout=10).status


def await_webhook(path, timeout=180):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        try:
            webhook(path, {}, secret=False)
            return
        except urllib.error.HTTPError as error:
            if error.code != 404:
                return
        except OSError:
            pass
        time.sleep(2)
    raise AssertionError("Webhook " + path + " never registered")


def await_state(predicate, timeout=40):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        state = mock()
        if predicate(state):
            return state
        time.sleep(1)
    raise AssertionError("Workflow timed out: " + json.dumps(state))


def cleanup(ids):
    listed = ",".join("'" + wid + "'" for wid in ids)
    docker("exec", "-T", "db", "psql", "-U", "hisaab", "-d", "n8n-local", "-c",
           f'UPDATE workflow_entity SET "activeVersionId" = NULL WHERE id IN ({listed})', capture=True)
    for table, column in [("workflow_published_version", '"workflowId"'),
                          ("workflow_history", '"workflowId"'), ("workflow_entity", "id")]:
        docker("exec", "-T", "db", "psql", "-U", "hisaab", "-d", "n8n-local", "-c",
               f"DELETE FROM {table} WHERE {column} IN ({listed})", capture=True)


def error_workflow_runs():
    sql = ('SELECT count(*) FROM execution_entity '
           "WHERE \"workflowId\" = 'testhisaabWF90err001'")
    return int(docker('exec', '-T', 'db', 'psql', '-U', 'hisaab', '-d', 'n8n-local', '-tAc', sql,
                      capture=True).stdout.strip() or 0)


def last_error_workflow_message():
    sql = ('SELECT d.data FROM execution_entity e JOIN execution_data d ON d."executionId" = e.id '
           "WHERE e.\"workflowId\" = 'testhisaabWF90err001' ORDER BY e.id DESC LIMIT 1")
    return docker('exec', '-T', 'db', 'psql', '-U', 'hisaab', '-d', 'n8n-local', '-tAc', sql,
                  capture=True).stdout


def freeze_execution():
    sql = ('SELECT e.status, d.data FROM execution_entity e JOIN execution_data d ON d."executionId" = e.id '
           "WHERE e.\"workflowId\" = 'testhisaabWF20mvp001' ORDER BY e.id DESC LIMIT 1")
    return docker('exec', '-T', 'db', 'psql', '-U', 'hisaab', '-d', 'n8n-local', '-tAc', sql, capture=True).stdout.strip()


def run_tests():
    files = list((ROOT / "n8n/workflows").glob("*.json"))
    ids = {json.loads(f.read_text(encoding="utf-8"))["id"]: "test" + json.loads(f.read_text(encoding="utf-8"))["id"] for f in files}
    cleanup(ids.values())
    with tempfile.TemporaryDirectory(prefix="hisaab-workflow-test-") as folder:
        for f in files:
            workflow = json.loads(f.read_text(encoding="utf-8"))
            # Rewrite only public bases, ids, paths and sub-workflow references.
            workflow = json.loads(json.dumps(workflow).replace("http://core:8000", "http://core:8300"))
            workflow["id"] = ids[workflow["id"]]
            workflow["name"] = "test/" + workflow["name"]
            # Point the isolated copies at the isolated WF90, or a test failure would land in
            # the product error workflow and read as a real one.
            if workflow["settings"].get("errorWorkflow") in ids:
                workflow["settings"]["errorWorkflow"] = ids[workflow["settings"]["errorWorkflow"]]
            schedule = {n["name"] for n in workflow["nodes"] if n["type"].endswith("scheduleTrigger")}
            workflow["nodes"] = [n for n in workflow["nodes"] if n["name"] not in schedule]
            for name in schedule:
                workflow["connections"].pop(name, None)
            for node in workflow["nodes"]:
                if node["type"].endswith("webhook"):
                    node["parameters"]["path"] = "test/" + node["parameters"]["path"]
                    node["webhookId"] = "test-" + node["webhookId"]
                if node["type"].endswith("executeWorkflow"):
                    node["parameters"]["workflowId"] = ids[node["parameters"]["workflowId"]]
                if node['name'] == 'Freeze context':
                    # Exercise exhaustion quickly in the isolated copy; product still allows 120 polls.
                    node['parameters']['jsCode'] = node['parameters']['jsCode'].replace(
                        'max_polls: 120', "max_polls: b.case_id === 'CASE-TIMEOUT' ? 2 : 120")
            Path(folder, f.name).write_text(json.dumps(workflow), encoding="utf-8")
        docker("cp", folder + "/.", "n8n:/tmp/hisaab-workflow-test")
        docker("exec", "-T", "n8n", "n8n", "import:workflow", "--separate", "--input=/tmp/hisaab-workflow-test")
        for wid in ids.values():
            docker("exec", "-T", "n8n", "n8n", "publish:workflow", "--id=" + wid)
    docker("restart", "n8n")
    # n8n answers healthz seconds before it registers webhooks, and a sleep long enough on a warm
    # machine is short on a cold one: a 404 here reads as a missing workflow, not a late one.
    # The unauthenticated probe below is a 401 or 403 once registered, so wait for it to stop 404ing.
    await_webhook("hisaab/wf10-nightly")
    try:
        mock("/test/reset", {})
        try:
            webhook("hisaab/wf10-nightly", {"merchant_id": "MID_TEST"}, secret=False)
            raise AssertionError("Unauthenticated nightly webhook was accepted")
        except urllib.error.HTTPError as error:
            assert error.code in (401, 403)
        webhook("hisaab/wf10-nightly", {"merchant_id": "MID_TEST", "as_of": "2026-03-10T02:00:00+05:30"})
        state = await_state(lambda s: len(s["questions"]) == 2)
        assert len(state["proposals"]) == 3
        assert [p["proposal"]["source"] for p in state["proposals"]] == ["rule", "agent", "rule"]
        assert state["pages"] == [None, "page2"], state["pages"]
        assert state['question_reads'] == ['MID_TEST'], 'WF10 duplicated its shared question read'
        # The window is now asked for, not filtered out afterwards, so assert what WF10 asked:
        # the two IST days before business time, as instants, and one probe for as_of.
        assert state["windows"] == [{"from": None, "to": None, "limit": "1"},
            {"from": "2026-03-07T18:30:00.000Z", "to": "2026-03-09T18:30:00.000Z",
             "limit": "200"}], state["windows"]
        assert all(h["as_of"] == "2026-03-09T12:00:00+05:30" for h in state["histories"])
        assert all(p["proposal"]["confidence"] <= 0.85 for p in state["proposals"] if p["proposal"]["source"] == "agent")
        assert {p['txn_id'] for p in state['proposals']} == {'T1', 'T2', 'T3'}
        print("PASS: WF10 asks for its IST window (old/end-boundary credits never fetched), pagination, prior history, rule/Sarvam-fake branches, proposals, questions, WF30", flush=True)
        # Tap the second question, then replay it. Neither request may answer the first.
        q = state["questions"][1]
        envelope = {"merchant_id": "MID_TEST", "message_id": "test-tap", "content_type": "text",
            "text": json.dumps({"type": "question_answer", "question_id": q["question"]["question_id"], "txn_id": q["txn_id"], "answer": "family"}),
            "language": "kn-IN", "sim_at": "2026-03-10T02:00:00+05:30"}
        webhook("hisaab/wf31-assistant", envelope)
        state = await_state(lambda s: len(s["claims"]) == 1)
        assert state["claims"][0]["txn_id"] == q["txn_id"]
        assert "label" not in state["claims"][0]["claim"]
        webhook("hisaab/wf31-assistant", envelope)
        time.sleep(3)
        assert len(mock()["claims"]) == 1
        print("PASS: explicit app question identity, answer payload, stale tap rejected")
        webhook("hisaab/wf10-nightly", {"merchant_id": "MID_TEST"})
        time.sleep(3)
        assert len(mock()["proposals"]) == 3 and len(mock()["questions"]) == 2
        print("PASS: a rerun does not reclassify or reask already labelled credits")
        webhook("hisaab/wf20-freeze", {"case_id": "CASE-TEST", "merchant_id": "MID_TEST", "opened_at": "2026-03-10T02:00:00+05:30"})
        state = await_state(lambda s: "CASE-TEST" in s["packs"])
        time.sleep(7)
        assert not mock()["deliveries"]
        mock("/test/decision", {"case_id": "CASE-TEST", "status": "approved"})
        state = await_state(lambda s: len(s["deliveries"]) == 1)
        assert state["deliveries"][0]["destination"] == "bank-nodal-and-ncrp"
        print("PASS: freeze pack waits for core approval before simulated send")
        webhook("hisaab/wf20-freeze", {"case_id": "CASE-REJECT", "merchant_id": "MID_TEST", "opened_at": "2026-03-10T02:00:00+05:30"})
        await_state(lambda s: "CASE-REJECT" in s["packs"])
        mock("/test/decision", {"case_id": "CASE-REJECT", "status": "rejected"})
        time.sleep(7)
        assert len(mock()["deliveries"]) == 1
        print("PASS: rejected pack is never sent")
        body = {"case_id": "CASE-TIMEOUT", "merchant_id": "MID_TEST", "opened_at": NOW}
        webhook("hisaab/wf20-freeze", body)
        await_state(lambda s: s['polls'].count('CASE-TIMEOUT') == 2)
        time.sleep(7)
        state = mock()
        assert state['polls'].count('CASE-TIMEOUT') == 2 and len(state['deliveries']) == 1
        expired = freeze_execution()
        assert expired.startswith('error|') and 'Approval wait expired' in expired, expired[:300]
        mock('/test/decision', {'case_id': 'CASE-TIMEOUT', 'status': 'approved'})
        webhook('hisaab/wf20-freeze', body)
        await_state(lambda s: len(s['deliveries']) == 2)
        webhook('hisaab/wf20-freeze', body)
        time.sleep(7)
        assert len(mock()['deliveries']) == 2
        print('PASS: approval wait stops at its budget; retry reads approval and sent retries do not send again')
        # 7.2: the expired WF20 above is a real failure, so WF90 must have picked it up and
        # named the workflow and the node rather than re-printing a stack.
        assert error_workflow_runs() >= 1, 'WF90 did not run for the failed WF20'
        reported = last_error_workflow_message()
        assert 'WF20 freeze-response' in reported and 'Approval wait expired' in reported, reported[:400]
        print('PASS: WF90 receives a real failure and names the workflow, node and message')
    finally:
        cleanup(ids.values())
        docker("restart", "n8n")


def main():
    # Stop only an earlier copy of this exact test helper, including one left by a failed run.
    docker("exec", "-T", "core", ".venv/bin/python", "-c", r"""
import os, pathlib, signal
for process in pathlib.Path('/proc').iterdir():
    if process.name.isdigit():
        try:
            args = (process / 'cmdline').read_bytes().split(b'\0')
            if b'/tmp/hisaab-mock-core.py' in args:
                os.kill(int(process.name), signal.SIGTERM)
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            pass
""", capture=True)
    docker("cp", str(ROOT / "n8n/tests/mock_core.py"), "core:/tmp/hisaab-mock-core.py")
    server = subprocess.Popen(["docker", "compose", "exec", "-T", "core", ".venv/bin/python",
                               "/tmp/hisaab-mock-core.py"], cwd=ROOT)
    try:
        for attempt in range(10):
            try:
                mock()
                break
            except subprocess.CalledProcessError:
                time.sleep(1)
        else:
            raise RuntimeError("Test API did not start")
        run_tests()
    finally:
        mock("/test/shutdown", {})
        server.wait(timeout=10)


if __name__ == "__main__":
    main()
