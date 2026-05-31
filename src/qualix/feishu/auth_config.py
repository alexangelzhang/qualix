"""Qualix-owned Lark auth configuration helpers."""

from __future__ import annotations

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

from qualix.constants import (
    QUALIX_LARK_AUTH_CONFIG,
    QUALIX_LARK_EMAIL_ENV,
    QUALIX_LARK_EXPIRES_ENV,
    QUALIX_LARK_TOKEN_ENV,
)


@dataclass(frozen=True)
class LarkAuthConfig:
    user_token: str = ""
    email: str = "unknown"
    token_expired_at: int = 0
    source: str = ""


def lark_auth_config_path() -> Path:
    return Path.home() / QUALIX_LARK_AUTH_CONFIG


def load_lark_auth_config() -> LarkAuthConfig:
    env_token = os.getenv(QUALIX_LARK_TOKEN_ENV, "")
    if env_token:
        return LarkAuthConfig(
            user_token=env_token,
            email=os.getenv(QUALIX_LARK_EMAIL_ENV, "unknown") or "unknown",
            token_expired_at=_parse_int(os.getenv(QUALIX_LARK_EXPIRES_ENV, "0")),
            source=f"env:{QUALIX_LARK_TOKEN_ENV}",
        )

    path = lark_auth_config_path()
    if not path.exists():
        return LarkAuthConfig(source=str(path))

    config = configparser.ConfigParser()
    config.read(path)
    return LarkAuthConfig(
        user_token=config.get("lark", "user_token", fallback="") or "",
        email=config.get("lark", "email", fallback="unknown") or "unknown",
        token_expired_at=_parse_int(config.get("lark", "token_expired_at", fallback="0")),
        source=str(path),
    )


def _parse_int(value: str | None) -> int:
    try:
        return int(value or 0)
    except ValueError:
        return 0
