# ENV_VARS: ["HISAAB_API", "HISAAB_KEY"]
"""Throwaway Phinite diagnostic. Publish it, test it, delete it.

It answers the questions the whole tool contract rests on, without needing a
graph, a channel, or our data service to be live:

  1. Can a tool reach the public internet at all? If not, every one of the 13
     tools is dead and the data-service architecture has to be rethought.
  2. Which HTTP libraries exist in the sandbox? (Decides whether handlers can
     use requests, or must stay on stdlib urllib.)
  3. Does the `# ENV_VARS:` header actually inject env variables?
  4. Is `capture_variables` or `captured_variables` the key Phinite reads?
     It returns both; whichever populates in the test output is the real one.
"""
import sys
import urllib.error
import urllib.request

TIMEOUT = 15


def _probe(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return {
                "ok": True,
                "status": getattr(r, "status", None),
                "body": r.read(300).decode("utf-8", "replace"),
            }
    except urllib.error.HTTPError as e:
        return {
            "ok": False,
            "status": e.code,
            "body": e.read(200).decode("utf-8", "replace"),
        }
    except Exception as e:  # noqa: BLE001 - this tool must never raise
        return {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}


def main(inputs, env_variables):
    env_variables = env_variables or {}

    libs = {}
    for mod in ("urllib.request", "json", "requests", "httpx", "sqlite3"):
        try:
            __import__(mod)
            libs[mod] = True
        except Exception:
            libs[mod] = False

    out = {
        "python": sys.version.split()[0],
        "libs": libs,
        "env_header_works": {
            "HISAAB_API_seen": bool(env_variables.get("HISAAB_API")),
            "HISAAB_KEY_seen": bool(env_variables.get("HISAAB_KEY")),
            "env_keys_visible": sorted(env_variables.keys()),
        },
        "public_get": _probe("https://api.github.com/zen"),
    }

    api = (env_variables.get("HISAAB_API") or "").rstrip("/")
    if api:
        out["service_health"] = _probe(
            api + "/health", {"X-Hisaab-Key": env_variables.get("HISAAB_KEY", "")}
        )

    probe = {
        "egress_ok": bool(out["public_get"].get("ok")),
        "python_version": out["python"],
        "which_key_won": "if you can see this, THIS key is the one Phinite reads",
    }
    return {
        "output": out,
        "capture_variables": probe,
        "captured_variables": probe,
    }
