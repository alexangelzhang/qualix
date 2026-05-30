"""qualix-run auth status — 检查飞书认证状态."""

from __future__ import annotations

import configparser
import time
from pathlib import Path

_VAF_CONFIG = Path.home() / ".vaf" / "config"


def run_auth_status() -> int:
    """执行 qualix-run auth status."""
    if not _VAF_CONFIG.exists():
        print("✗ 未检测到 larkkit 配置（~/.vaf/config 不存在）")
        print("  请先安装 larkkit 并登录：uvx larkkit auth login")
        return 1

    config = configparser.ConfigParser()
    config.read(_VAF_CONFIG)
    user_token = config.get("feishu", "user_token", fallback="")
    token_expired_at = config.get("feishu", "token_expired_at", fallback="0")

    if not user_token:
        print("✗ 未登录，请执行：uvx larkkit auth login")
        return 1

    now = int(time.time())
    expired_at = int(token_expired_at)
    if now >= expired_at:
        print("⚠ token 已过期，请执行：uvx larkkit auth refresh")
        print("  或重新登录：uvx larkkit auth login")
        return 1

    minutes_left = max(0, (expired_at - now) // 60)
    print(f"✓ 飞书认证有效（剩余 {minutes_left} 分钟）")
    print(f"  配置文件: {_VAF_CONFIG}")
    print("  DQG 将自动使用此 token 上报团队数据")
    return 0
