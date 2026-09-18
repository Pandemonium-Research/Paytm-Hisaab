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
            Path(folder, f.name).write_text(json.dumps(workflow), encoding="utf-8")
        docker("cp", folder + "/.", "n8n:/tmp/hisaab-workflow-test")
        docker("exec", "-T", "n8n", "n8n", "import:workflow", "--separate", "--input=/tmp/hisaab-workflow-test")
        for wid in ids.values():
            docker("exec", "-T", "n8n", "n8n", "publish:workflow", "--id=" + wid)
    docker("restart", "n8n")
    time.sleep(12)
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
        assert all(h["as_of"] == "2026-03-09T12:00:00+05:30" for h in state["histories"])
        assert all(p["proposal"]["confidence"] <= 0.85 for p in state["proposals"] if p["proposal"]["source"] == "agent")
        assert {p['txn_id'] for p in state['proposals']} == {'T1', 'T2', 'T3'}
        print("PASS: IST window excludes old/end-boundary credits, pagination, prior history, rule/Sarvam-fake branches, proposals, questions, WF30", flush=True)
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
