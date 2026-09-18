#!/usr/bin/env python3
"""Cross-platform task runner using only argparse and subprocess.

The implementation plan names Invoke. This deliberately uses the standard library so a fresh
clone can run it before Python packages are installed, on macOS and Windows alike.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
RUNTIME_DIR = ROOT / "services" / "core" / "runtime"
TUNNEL_URL_FILE = RUNTIME_DIR / "tunnel-url.txt"
CONFIG_FILE = RUNTIME_DIR / "config.json"
TUNNEL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")


def load_env_file(path: Path, environment: dict[str, str]) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip()
        if value[:1] == value[-1:] and value[:1] in {"'", '"'}:
            value = value[1:-1]
        environment[name] = value


def command_env(live: bool) -> dict[str, str]:
    environment = os.environ.copy()
    load_env_file(ROOT / ".env", environment)
    if live:
        live_file = ROOT / ".env.live"
        if not live_file.exists():
            raise SystemExit("--live requires .env.live; real keys are never loaded otherwise")
        load_env_file(live_file, environment)
    environment.setdefault("HISAAB_LIVE", "0")
    return environment


def run(command: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print("+", subprocess.list2cmdline(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def compose(args: list[str], environment: dict[str, str]) -> None:
    run(["docker", "compose", *args], env=environment)


def cmd_up(args: argparse.Namespace, environment: dict[str, str]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    command: list[str] = []
    if args.surfaces:
        command += ["--profile", "surfaces"]
    if args.local_n8n:
        command += ["--profile", "local-n8n"]
    compose([*command, "up", "--build", "--detach", "--wait"], environment)


def cmd_down(args: argparse.Namespace, environment: dict[str, str]) -> None:
    command = ["down"]
    if args.volumes:
        command.append("--volumes")
    compose(command, environment)


def cmd_logs(args: argparse.Namespace, environment: dict[str, str]) -> None:
    command = ["logs", "--follow", "--tail", str(args.tail)]
    if args.service:
        command.append(args.service)
    compose(command, environment)


def cmd_migrate(_args: argparse.Namespace, _environment: dict[str, str]) -> None:
    print("Migrations are a no-op until task 2A.3 lands.")


def cmd_test(_args: argparse.Namespace, environment: dict[str, str]) -> None:
    # Tests are intentionally local even if --live was supplied; no test may spend credits.
    environment = environment.copy()
    environment["HISAAB_LIVE"] = "0"
    run(["uv", "run", "pytest"], cwd=ROOT / "services" / "core", env=environment)


def cmd_generate(args: argparse.Namespace, environment: dict[str, str]) -> None:
    command = [sys.executable, "-m", "sim.generate"]
    if args.only:
        command += ["--only", args.only]
    if args.out:
        command += ["--out", args.out]
    if args.force:
        # sim.generate refuses to overwrite a split it did not write; this is the way past that.
        command.append("--force")
    run(command, env=environment)


def cmd_tunnel(_args: argparse.Namespace, environment: dict[str, str]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    command = [
        "cloudflared",
        "tunnel",
        "--protocol",
        "http2",
        "--url",
        "http://localhost:8080",
    ]
    print("+", subprocess.list2cmdline(command), flush=True)
    try:
        process = subprocess.Popen(
            command,
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError as exc:
        raise SystemExit("cloudflared is not installed or is not on PATH") from exc

    assert process.stdout is not None
    try:
        for line in process.stdout:
            print(line, end="", flush=True)
            if match := TUNNEL_PATTERN.search(line):
                TUNNEL_URL_FILE.write_text(match.group(0) + "\n", encoding="utf-8")
                print("Tunnel URL captured. Run `python tasks.py publish` in another terminal.")
    except KeyboardInterrupt:
        process.terminate()
    finally:
        try:
            return_code = process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            return_code = process.wait()
    if return_code not in {0, -2, 130, 143}:
        raise SystemExit(return_code)


def _read_runtime_url(explicit: str | None, environment: dict[str, str]) -> str:
    candidates = [explicit, environment.get("PUBLIC_URL")]
    if TUNNEL_URL_FILE.exists():
        candidates.append(TUNNEL_URL_FILE.read_text(encoding="utf-8").strip())
    for candidate in candidates:
        if candidate and candidate.startswith("https://"):
            return candidate.rstrip("/")
    raise SystemExit(
        "No HTTPS tunnel URL found. Start `python tasks.py tunnel` or pass `publish --url URL`."
    )


def _request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    request_headers = {"Accept": "application/json", **(headers or {})}
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {url} failed with HTTP {exc.code}: {detail}") from exc


def _require_live(environment: dict[str, str], operation: str) -> None:
    if environment.get("HISAAB_LIVE") != "1":
        raise RuntimeError(f"{operation} refused: HISAAB_LIVE must be 1")


def _rewrite_urls(value: Any, old_urls: set[str], new_url: str) -> tuple[Any, int]:
    if isinstance(value, str):
        rewritten = value
        for old in old_urls:
            rewritten = rewritten.replace(old.rstrip("/"), new_url)
        return rewritten, int(rewritten != value)
    if isinstance(value, list):
        output, count = [], 0
        for item in value:
            changed, item_count = _rewrite_urls(item, old_urls, new_url)
            output.append(changed)
            count += item_count
        return output, count
    if isinstance(value, dict):
        output, count = {}, 0
        for key, item in value.items():
            changed, item_count = _rewrite_urls(item, old_urls, new_url)
            output[key] = changed
            count += item_count
        return output, count
    return value, 0


def _publish_n8n(url: str, old_url: str, environment: dict[str, str]) -> None:
    _require_live(environment, "n8n Cloud publish")
    base = environment.get("N8N_BASE_URL", "").rstrip("/")
    api_key = environment.get("N8N_API_KEY", "")
    workflow_ids = [item.strip() for item in environment.get("N8N_WORKFLOW_IDS", "").split(",") if item.strip()]
    if not base.startswith("https://") or not api_key or not workflow_ids:
        raise RuntimeError(
            "live publish needs HTTPS N8N_BASE_URL, N8N_API_KEY and N8N_WORKFLOW_IDS"
        )
    headers = {"X-N8N-API-KEY": api_key}
    placeholders = {environment.get("N8N_PUBLIC_BASE_PLACEHOLDER", "https://hisaab.invalid")}
    if old_url:
        placeholders.add(old_url)
    total = 0
    for workflow_id in workflow_ids:
        workflow = _request_json(f"{base}/api/v1/workflows/{workflow_id}", headers=headers)
        rewritten, count = _rewrite_urls(workflow, placeholders, url)
        if count == 0:
            raise RuntimeError(f"n8n workflow {workflow_id} contains no known public-URL placeholder")
        payload = {
            key: rewritten[key]
            for key in ("name", "nodes", "connections", "settings", "staticData")
            if key in rewritten
        }
        _request_json(
            f"{base}/api/v1/workflows/{workflow_id}",
            method="PUT",
            headers=headers,
            body=payload,
        )
        total += count
    print(f"Updated {len(workflow_ids)} n8n Cloud workflow(s), replacing {total} URL value(s).")


def _publish_twilio(environment: dict[str, str]) -> None:
    _require_live(environment, "Twilio sandbox publish")
    config_url = environment.get("TWILIO_SANDBOX_CONFIG_URL", "")
    webhook_url = environment.get("N8N_WHATSAPP_WEBHOOK_URL", "")
    account_sid = environment.get("TWILIO_ACCOUNT_SID", "")
    auth_token = environment.get("TWILIO_AUTH_TOKEN", "")
    if not all((config_url.startswith("https://"), webhook_url.startswith("https://"), account_sid, auth_token)):
        raise RuntimeError(
            "live publish needs TWILIO_SANDBOX_CONFIG_URL, N8N_WHATSAPP_WEBHOOK_URL and Twilio credentials"
        )
    field = environment.get("TWILIO_SANDBOX_WEBHOOK_FIELD", "Url")
    data = urllib.parse.urlencode({field: webhook_url}).encode("utf-8")
    credentials = base64.b64encode(f"{account_sid}:{auth_token}".encode()).decode()
    request = urllib.request.Request(
        config_url,
        data=data,
        headers={"Authorization": f"Basic {credentials}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            if response.status >= 300:
                raise RuntimeError(f"Twilio sandbox update returned HTTP {response.status}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Twilio sandbox update failed with HTTP {exc.code}: {detail}") from exc
    print("Updated the Twilio sandbox inbound webhook.")


def cmd_publish(args: argparse.Namespace, environment: dict[str, str]) -> None:
    if args.live and environment.get("HISAAB_LIVE") != "1":
        raise SystemExit("live publish refused: .env.live must set HISAAB_LIVE=1")
    url = _read_runtime_url(args.url, environment)
    old_url = ""
    if CONFIG_FILE.exists():
        try:
            old_url = json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("public_url", "")
        except json.JSONDecodeError:
            pass
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG_FILE.with_suffix(".tmp")
    temporary.write_text(json.dumps({"public_url": url}, indent=2) + "\n", encoding="utf-8")
    temporary.replace(CONFIG_FILE)
    print(f"Core public URL set to {url}")

    if not args.live:
        print("Local publish complete. n8n Cloud and Twilio were not contacted.")
        return
    _publish_n8n(url, old_url, environment)
    _publish_twilio(environment)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Paytm Hisaab development tasks")
    result.add_argument(
        "--live",
        action="store_true",
        help="load .env.live; paid-provider commands still require HISAAB_LIVE=1",
    )
    subcommands = result.add_subparsers(dest="command", required=True)

    up = subcommands.add_parser("up", help="build and start the local core stack")
    up.add_argument("--surfaces", action="store_true", help="also start memory and web")
    up.add_argument("--local-n8n", action="store_true", help="also start local n8n")
    up.set_defaults(func=cmd_up)

    down = subcommands.add_parser("down", help="stop the local stack")
    down.add_argument("--volumes", action="store_true", help="also remove named data volumes")
    down.set_defaults(func=cmd_down)

    logs = subcommands.add_parser("logs", help="follow Compose logs")
    logs.add_argument("service", nargs="?", help="optional service name")
    logs.add_argument("--tail", type=int, default=100, help="initial lines per service")
    logs.set_defaults(func=cmd_logs)

    migrate = subcommands.add_parser("migrate", help="run database migrations (2A.3 placeholder)")
    migrate.set_defaults(func=cmd_migrate)

    test = subcommands.add_parser("test", help="run the core test suite with uv")
    test.set_defaults(func=cmd_test)

    tunnel = subcommands.add_parser("tunnel", help="start the HTTP/2 Cloudflare quick tunnel")
    tunnel.set_defaults(func=cmd_tunnel)

    publish = subcommands.add_parser("publish", help="publish the captured tunnel hostname")
    publish.add_argument("--url", help="HTTPS tunnel URL; otherwise use the captured URL")
    publish.set_defaults(func=cmd_publish)

    generate = subcommands.add_parser("generate", help="generate deterministic simulator data")
    generate.add_argument("--only", choices=("demo", "dev", "eval", "sweep"), help="generate one split")
    generate.add_argument("--out", help="output root (sim.generate defaults to data)")
    generate.add_argument("--force", action="store_true", help="overwrite a split sim.generate did not write")
    generate.set_defaults(func=cmd_generate)
    return result


def main() -> None:
    args = parser().parse_args()
    environment = command_env(args.live)
    try:
        args.func(args, environment)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(exc.returncode) from None


if __name__ == "__main__":
    main()
