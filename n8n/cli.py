"""Load and save n8n workflows and credentials (task 1.5 tooling, owned by B).

    python n8n/cli.py import   [--target local|cloud] [--activate]
    python n8n/cli.py export   [--target local|cloud]
    python n8n/cli.py list     [--target local|cloud]

**local** talks to the n8n container through `docker compose exec`, using n8n's own CLI. That is
deliberate: the local n8n has no owner account, so its REST and public APIs refuse everything,
while the CLI works from the first boot. Two things the CLI insists on, both learned by hitting
them: a workflow file must carry a top-level `id`, and a credentials file must be a JSON array.

**cloud** uses the n8n public API with `N8N_BASE_URL` and `N8N_API_KEY`. It is only used inside
live window L2 (task 10.1b); nothing here spends credits on its own.

Exported workflows are written one file per workflow with sorted keys, so a re-export produces a
clean diff instead of a reshuffled blob.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW_DIR = ROOT / "n8n" / "workflows"
CREDENTIAL_FILE = ROOT / "n8n" / "credentials" / "local.json"
CONTAINER = "n8n"
CONTAINER_TMP = "/tmp/hisaab-n8n"


# --------------------------------------------------------------------------- shared

def load_env() -> dict[str, str]:
    """Read .env the way tasks.py does, so both agree on keys and URLs."""
    environment = dict(os.environ)
    env_file = ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            name, _, value = line.partition("=")
            environment.setdefault(name.strip(), value.strip())
    return environment


def run(command: list[str], **kwargs) -> subprocess.CompletedProcess:
    print("+", " ".join(command))
    return subprocess.run(command, cwd=ROOT, check=True, **kwargs)


def compose(*args: str, **kwargs) -> subprocess.CompletedProcess:
    return run(["docker", "compose", *args], **kwargs)


def n8n_cli(*args: str, capture: bool = False) -> str:
    """Run n8n's own CLI inside the container."""
    result = compose(
        "exec", "-T", CONTAINER, "n8n", *args,
        capture_output=capture, text=True if capture else None,
    )
    return (result.stdout or "") if capture else ""


def workflow_files() -> list[Path]:
    return sorted(WORKFLOW_DIR.glob("*.json"))


def write_workflow(path: Path, workflow: dict) -> None:
    path.write_text(json.dumps(workflow, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
                    encoding="utf-8")


# ---------------------------------------------------------------------------- local

def local_replace(ids: list[str]) -> None:
    """Drop our own workflows from the local dev database before importing.

    `import:workflow` only creates: it will not overwrite a workflow that already exists, and n8n
    2.x keeps a separate published version, so an edited file otherwise never reaches the running
    instance. There is no `delete:workflow` in the CLI. This touches only the ids in
    n8n/workflows/, and only on the local development instance - never Cloud.
    """
    if not ids:
        return
    listed = ", ".join("'" + i.replace("'", "") + "'" for i in ids)
    user = os.environ.get("POSTGRES_USER", "hisaab")
    # The published snapshot has to go first. n8n 2.x keeps it separately, and `publish:workflow`
    # restores it over a freshly imported workflow, so an edited file silently has no effect.
    statements = [
        f'delete from workflow_published_version where "workflowId" in ({listed})',
        f'delete from workflow_history where "workflowId" in ({listed})',
        f"delete from workflow_entity where id in ({listed})",
    ]
    for statement in statements:
        subprocess.run(["docker", "compose", "exec", "-T", "db", "psql", "-U", user,
                        "-d", "n8n-local", "-c", statement],
                       cwd=ROOT, capture_output=True, text=True)  # tolerate tables that differ by version


def wait_for_n8n(attempts: int = 40) -> None:
    """n8n registers webhooks at boot; posting before it is ready looks like a workflow bug."""
    for _ in range(attempts):
        try:
            with urllib.request.urlopen("http://localhost:5678/healthz", timeout=2) as response:
                if response.status == 200:
                    return
        except Exception:
            pass
        time.sleep(1)
    print("warning: n8n did not report healthy in time")


def local_import(activate: bool) -> None:
    if not workflow_files():
        sys.exit(f"no workflows in {WORKFLOW_DIR}")
    local_replace([json.loads(f.read_text(encoding="utf-8"))["id"] for f in workflow_files()])

    # Clear the staging directory as root: `docker compose cp` writes files owned by root, so a
    # plain `rm -rf` as the node user fails silently and n8n then re-imports yesterday's JSON.
    compose("exec", "-T", "-u", "0", CONTAINER, "sh", "-c",
            f"rm -rf {CONTAINER_TMP}; mkdir -p {CONTAINER_TMP}/workflows")
    # Copy file by file to fixed names, so each run overwrites instead of nesting a new directory.
    for source in workflow_files():
        compose("cp", str(source), f"{CONTAINER}:{CONTAINER_TMP}/workflows/{source.name}")
    if CREDENTIAL_FILE.exists():
        # The committed file is a template: real keys live in .env and must never reach git.
        environment = load_env()
        rendered = re.sub(r"\$\{([A-Z0-9_]+)\}",
                          lambda m: environment.get(m.group(1), ""),
                          CREDENTIAL_FILE.read_text(encoding="utf-8"))
        missing = [c["name"] for c in json.loads(rendered)
                   if not all(str(v).strip() for v in c["data"].values())]
        if missing:
            print("warning: no .env value for", ", ".join(missing))
        filled = Path(tempfile.mkdtemp(prefix="hisaab-cred-")) / "credentials.json"
        filled.write_text(rendered, encoding="utf-8")
        try:
            compose("cp", str(filled), f"{CONTAINER}:{CONTAINER_TMP}/credentials.json")
            n8n_cli("import:credentials", f"--input={CONTAINER_TMP}/credentials.json")
        finally:
            shutil.rmtree(filled.parent, ignore_errors=True)
    n8n_cli("import:workflow", "--separate", f"--input={CONTAINER_TMP}/workflows")

    if activate:
        for source in workflow_files():
            workflow = json.loads(source.read_text(encoding="utf-8"))
            # `update:workflow --active=true` is deprecated in 2.x; publish is the current verb.
            n8n_cli("publish:workflow", f"--id={workflow['id']}")
        # n8n registers webhooks at boot, so an activation only takes effect after a restart.
        compose("restart", CONTAINER)
        wait_for_n8n()
    print("imported", len(workflow_files()), "workflows")


def local_export() -> None:
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    compose("exec", "-T", CONTAINER, "sh", "-c", f"rm -rf {CONTAINER_TMP}/export; mkdir -p {CONTAINER_TMP}/export")
    n8n_cli("export:workflow", "--all", "--separate", f"--output={CONTAINER_TMP}/export")
    staging = Path(tempfile.mkdtemp(prefix="hisaab-n8n-"))
    try:
        compose("cp", f"{CONTAINER}:{CONTAINER_TMP}/export", str(staging / "export"))
        exported = sorted((staging / "export").glob("*.json"))
        for source in exported:
            workflow = json.loads(source.read_text(encoding="utf-8"))
            name = workflow.get("name", source.stem)
            slug = name.split("/")[-1].split()[0].lower()
            write_workflow(WORKFLOW_DIR / f"{slug}.json", workflow)
        print("exported", len(exported), "workflows to", WORKFLOW_DIR)
    finally:
        shutil.rmtree(staging, ignore_errors=True)


def local_list() -> None:
    print(n8n_cli("list:workflow", capture=True).strip())


# ---------------------------------------------------------------------------- cloud

def cloud_request(environment: dict[str, str], method: str, path: str, payload: dict | None = None) -> dict:
    base = environment.get("N8N_BASE_URL", "").rstrip("/")
    key = environment.get("N8N_API_KEY", "")
    if not base or not key:
        sys.exit("cloud target needs N8N_BASE_URL and N8N_API_KEY in .env")
    request = urllib.request.Request(
        f"{base}/api/v1{path}",
        method=method,
        data=json.dumps(payload).encode("utf-8") if payload is not None else None,
        headers={"X-N8N-API-KEY": key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def cloud_import(environment: dict[str, str], activate: bool) -> None:
    # Not exercised yet: Cloud is touched only in live window L2 (10.1b).
    for source in workflow_files():
        workflow = json.loads(source.read_text(encoding="utf-8"))
        body = {k: workflow[k] for k in ("name", "nodes", "connections", "settings") if k in workflow}
        created = cloud_request(environment, "POST", "/workflows", body)
        print("created", created.get("id"), workflow.get("name"))
        if activate and created.get("id"):
            cloud_request(environment, "POST", f"/workflows/{created['id']}/activate")


def cloud_export(environment: dict[str, str]) -> None:
    WORKFLOW_DIR.mkdir(parents=True, exist_ok=True)
    for workflow in cloud_request(environment, "GET", "/workflows?limit=200").get("data", []):
        slug = workflow.get("name", workflow["id"]).split("/")[-1].split()[0].lower()
        write_workflow(WORKFLOW_DIR / f"{slug}.json", workflow)


# ----------------------------------------------------------------------------- main

def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("import", "export", "list"))
    parser.add_argument("--target", choices=("local", "cloud"), default="local")
    parser.add_argument("--activate", action="store_true", help="activate every workflow after import")
    args = parser.parse_args(argv)
    environment = load_env()

    if args.target == "local":
        {"import": lambda: local_import(args.activate), "export": local_export, "list": local_list}[args.action]()
    else:
        if args.action == "import":
            cloud_import(environment, args.activate)
        elif args.action == "export":
            cloud_export(environment)
        else:
            for workflow in cloud_request(environment, "GET", "/workflows?limit=200").get("data", []):
                print(workflow["id"], "|", workflow.get("name"), "| active:", workflow.get("active"))


if __name__ == "__main__":
    main()
