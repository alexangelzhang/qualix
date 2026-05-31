"""qualix-run auth status — check optional Lark document-ingest auth."""

from __future__ import annotations

import time

from qualix.constants import QUALIX_LARK_TOKEN_ENV
from qualix.feishu.auth_config import lark_auth_config_path, load_lark_auth_config


def run_auth_status() -> int:
    """执行 qualix-run auth status."""
    auth = load_lark_auth_config()
    config_path = lark_auth_config_path()
    if not auth.user_token:
        print("✗ 未检测到 Lark/Feishu 文档摄入凭证")
        print(f"  可设置环境变量 {QUALIX_LARK_TOKEN_ENV}，或创建配置文件：{config_path}")
        print("  配置示例：")
        print("  [lark]")
        print("  user_token = <your user access token>")
        print("  email = you@example.com")
        print("  token_expired_at = 0")
        return 1

    now = int(time.time())
    expired_at = auth.token_expired_at
    if now >= expired_at:
        print("⚠ token 可能已过期，请刷新后更新 Qualix auth 配置")
        return 1

    minutes_left = max(0, (expired_at - now) // 60)
    print(f"✓ Lark/Feishu 文档摄入凭证有效（剩余 {minutes_left} 分钟）")
    print(f"  来源: {auth.source}")
    print("  Qualix 只会在你明确发起文档摄入时使用该凭证")
    return 0
