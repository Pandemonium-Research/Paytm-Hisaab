"""Role-key authentication shared by every protected route."""

from __future__ import annotations

import secrets
from collections.abc import Callable

from fastapi import Header, HTTPException

from .config import get_settings
from .schemas.ledger import EntryKind
from .schemas.roles import ENDPOINT_PERMISSIONS, ROLE_ENTRY_KINDS, Role


def _needed(roles: frozenset[Role]) -> str:
    return ", ".join(sorted(role.value for role in roles))


def role_for_key(key: str | None) -> Role | None:
    if key is None:
        return None
    for role, expected in get_settings().role_keys.items():
        if expected and secrets.compare_digest(key, expected):
            return role
    return None


def require_role(
    endpoint: str, entry_kind: EntryKind | None = None
) -> Callable[[str | None], Role]:
    """Build a FastAPI dependency for one contracted endpoint."""

    allowed = ENDPOINT_PERMISSIONS[endpoint]
    if entry_kind is not None and not any(
        entry_kind in ROLE_ENTRY_KINDS[role] for role in allowed
    ):
        raise RuntimeError(
            f"role contract for {endpoint} cannot append {entry_kind.value}"
        )

    def authorise(x_hisaab_key: str | None = Header(default=None)) -> Role:
        needed = _needed(allowed)
        if not x_hisaab_key:
            raise HTTPException(
                status_code=403,
                detail=f"X-Hisaab-Key is required; this endpoint needs role {needed}.",
            )
        role = role_for_key(x_hisaab_key)
        if role is None:
            raise HTTPException(
                status_code=403,
                detail=f"X-Hisaab-Key is not recognised; this endpoint needs role {needed}.",
            )
        if role not in allowed:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{role.value}' is not permitted; this endpoint needs role {needed}.",
            )
        if entry_kind is not None and entry_kind not in ROLE_ENTRY_KINDS[role]:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{role.value}' cannot append ledger entry {entry_kind.value}.",
            )
        return role

    return authorise
