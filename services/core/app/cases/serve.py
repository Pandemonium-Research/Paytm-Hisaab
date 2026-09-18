"""Serve recorded pack artifacts at their opaque URLs."""

from __future__ import annotations

from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import text

from ..clock import sim_now
from .artifacts import pack_dir


def _pack_row(connection, pack_id: str, suffix: str):
    as_of = sim_now(connection)
    row = connection.execute(
        text("""SELECT p.*, c.opened_at FROM ops.packs p
                JOIN ops.cases c ON c.case_id = p.case_id AND c.merchant_id = p.merchant_id
                WHERE p.pack_id = :pack AND p.built_at <= :as_of AND c.opened_at <= :as_of"""),
        {"pack": pack_id, "as_of": as_of},
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, f"No pack {pack_id} at the current business time.")
    data = row["data"] or {}
    key = "json_path" if suffix == "json" else "pdf_path"
    stored = data.get(key)
    if not stored:
        raise HTTPException(404, f"Pack {pack_id} has no {suffix} artifact.")
    path = Path(stored)
    expected_root = pack_dir().resolve()
    resolved = path.resolve()
    if not resolved.is_relative_to(expected_root):
        raise HTTPException(404, "Artifact path is not allowed.")
    if not resolved.is_file() or resolved.name != f"{pack_id}.{suffix}":
        raise HTTPException(404, f"Pack {pack_id} artifact is missing.")
    return resolved


def artifact_response(connection, pack_id: str, suffix: str):
    path = _pack_row(connection, pack_id, suffix)
    media = "application/json" if suffix == "json" else "application/pdf"
    return FileResponse(path, media_type=media, filename=path.name)
