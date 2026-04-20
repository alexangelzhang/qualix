"""Credential Pool：多凭证轮转 + 429 自动 failover.

支持多个 API key 配置，429 限流时自动轮转到下一个 key。
借鉴 Hermes Agent 的 credential_pool.py 设计。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from dqg.log import get_logger

log = get_logger(__name__)

# 冷却时间
_RATE_LIMIT_COOLDOWN = 3600  # 429 → 1 小时
_QUOTA_EXHAUSTED_COOLDOWN = 86400  # 402 → 24 小时


@dataclass
class Credential:
    """单个凭证."""
    api_key: str
    provider: str = "anthropic"
    use_count: int = 0
    cooldown_until: float = 0.0
    last_error: str = ""

    @property
    def is_available(self) -> bool:
        return time.time() >= self.cooldown_until


@dataclass
class CredentialPool:
    """多凭证池，支持轮转和 failover."""

    credentials: list[Credential] = field(default_factory=list)
    strategy: str = "least_used"  # least_used / round_robin / random

    _current_index: int = 0

    def add(self, api_key: str, provider: str = "anthropic") -> None:
        """添加凭证."""
        self.credentials.append(Credential(api_key=api_key, provider=provider))

    def acquire(self) -> Credential | None:
        """获取一个可用凭证."""
        available = [c for c in self.credentials if c.is_available]
        if not available:
            # 所有凭证都在冷却中
            next_available = min(c.cooldown_until for c in self.credentials) if self.credentials else 0
            wait = max(0, next_available - time.time())
            log.warning("All credentials in cooldown, next available in %.0fs", wait)
            return None

        if self.strategy == "least_used":
            selected = min(available, key=lambda c: c.use_count)
        elif self.strategy == "round_robin":
            self._current_index = self._current_index % len(available)
            selected = available[self._current_index]
            self._current_index += 1
        else:  # random
            import random
            selected = random.choice(available)

        selected.use_count += 1
        return selected

    def report_error(self, credential: Credential, status_code: int, error: str = "") -> None:
        """报告凭证错误，触发冷却."""
        credential.last_error = error
        if status_code == 429:
            credential.cooldown_until = time.time() + _RATE_LIMIT_COOLDOWN
            log.warning("Credential rate limited (429), cooldown 1h: %s...%s",
                       credential.api_key[:8], credential.api_key[-4:])
        elif status_code == 402:
            credential.cooldown_until = time.time() + _QUOTA_EXHAUSTED_COOLDOWN
            log.warning("Credential quota exhausted (402), cooldown 24h: %s...%s",
                       credential.api_key[:8], credential.api_key[-4:])

    def report_success(self, credential: Credential) -> None:
        """报告成功，清除错误状态."""
        credential.last_error = ""

    @property
    def available_count(self) -> int:
        return sum(1 for c in self.credentials if c.is_available)

    @property
    def total_count(self) -> int:
        return len(self.credentials)

    def stats(self) -> dict[str, Any]:
        return {
            "total": self.total_count,
            "available": self.available_count,
            "strategy": self.strategy,
            "credentials": [
                {
                    "provider": c.provider,
                    "key_prefix": c.api_key[:8] + "...",
                    "use_count": c.use_count,
                    "available": c.is_available,
                    "last_error": c.last_error,
                }
                for c in self.credentials
            ],
        }


# ---------------------------------------------------------------------------
# 全局池（单例）
# ---------------------------------------------------------------------------

_pool: CredentialPool | None = None


def get_credential_pool() -> CredentialPool:
    """获取全局凭证池."""
    global _pool
    if _pool is None:
        _pool = CredentialPool()
        _init_from_env()
    return _pool


def _init_from_env() -> None:
    """从环境变量初始化凭证池."""
    import os

    pool = get_credential_pool()

    # ANTHROPIC_API_KEY（主 key）
    main_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if main_key:
        pool.add(main_key, "anthropic")

    # ANTHROPIC_API_KEY_2, _3, ... （额外 key）
    for i in range(2, 10):
        extra_key = os.environ.get(f"ANTHROPIC_API_KEY_{i}", "")
        if extra_key:
            pool.add(extra_key, "anthropic")

    # OPENAI_API_KEY（用于 DeepEval 等）
    openai_key = os.environ.get("OPENAI_API_KEY", "")
    if openai_key:
        pool.add(openai_key, "openai")

    if pool.total_count > 1:
        log.info("Credential pool initialized: %d keys", pool.total_count)
