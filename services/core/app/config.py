"""Environment-backed settings for the core service."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

from .schemas.roles import Role


def _boolean(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    environment: str
    hisaab_live: bool
    default_locale: str
    supported_locales: tuple[str, ...]
    vapid_public_key: str | None
    public_url: str
    database_url: str
    role_keys: dict[Role, str]

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            environment=os.getenv("HISAAB_ENV", "local"),
            hisaab_live=_boolean("HISAAB_LIVE"),
            default_locale=os.getenv("DEFAULT_LOCALE", "en-IN"),
            supported_locales=tuple(
                item.strip()
                for item in os.getenv("SUPPORTED_LOCALES", "en-IN,kn-IN,hi-IN").split(",")
                if item.strip()
            ),
            vapid_public_key=os.getenv("VAPID_PUBLIC_KEY") or None,
            public_url=_public_url(),
            database_url=os.getenv(
                "DATABASE_URL", "postgresql://hisaab:hisaab@db:5432/hisaab"
            ),
            role_keys={
                role: os.getenv(f"KEY_{role.value.upper()}", f"dev-{role.value}")
                for role in Role
            },
        )


def _public_url() -> str:
    value = os.getenv("PUBLIC_URL", "").strip()
    if value:
        return value

    # publish writes a small runtime file so the tunnel URL survives a core restart without
    # putting an ephemeral hostname or a real secret into the everyday environment file.
    path = Path(os.getenv("HISAAB_RUNTIME_CONFIG", "/runtime/config.json"))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return ""
    return str(data.get("public_url", "")).strip()


def get_settings() -> Settings:
    # Do not cache this: publish may update the runtime URL while the process is running.
    return Settings.from_environment()


def require_live(operation: str) -> None:
    if not get_settings().hisaab_live:
        raise RuntimeError(
            f"{operation} can reach a paid provider and is disabled while HISAAB_LIVE is not 1"
        )
