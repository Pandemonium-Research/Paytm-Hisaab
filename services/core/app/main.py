"""Paytm Hisaab core API."""

from __future__ import annotations

import os
import subprocess

from fastapi import FastAPI

from .routers import app_screens, assistant, cases, guards, ledger_ops, ops, prompts, rails, reads, sim, skills


app = FastAPI(
    title="Paytm Hisaab core",
    version="0.1.0",
    root_path="/api",
    description="Persistent payment/question API for the prototype; remaining backlog routes serve fixtures.",
)

for router in (
    rails.router,
    reads.router,
    skills.router,
    ledger_ops.router,
    cases.router,
    guards.router,
    ops.router,
    app_screens.router,
    assistant.router,
    sim.router,
    prompts.router,
):
    app.include_router(router)


def _git_sha() -> str | None:
    if value := os.getenv("GIT_SHA"):
        return value
    try:
        return subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=0.2,
        ).stdout.strip() or None
    except (FileNotFoundError, subprocess.SubprocessError):
        return None


@app.get("/healthz", tags=["health"])
async def healthz() -> dict[str, bool | str]:
    result: dict[str, bool | str] = {"ok": True}
    if sha := _git_sha():
        result["git_sha"] = sha
    return result
