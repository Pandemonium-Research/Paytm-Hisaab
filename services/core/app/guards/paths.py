"""Repository paths resolved from source location, not the process cwd."""

from __future__ import annotations

from pathlib import Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[4]


def default_citations_path() -> Path:
    return repo_root() / "legal" / "citations.yaml"
