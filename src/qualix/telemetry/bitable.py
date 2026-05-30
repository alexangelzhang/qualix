"""DQG bitable 上报模块.

bitable token 由 DQG 维护者统一预置，用户无需配置。
依赖 DQG feishu client（~/.dqg/feishu_token.json），不依赖 larkkit。
失败静默，不阻断主流程。
"""

from __future__ import annotations

import time
from typing import Any

# ============ DQG 公共埋点表（维护者统一预置）============
_BASE_TOKEN = "FQtabFSMTauogmstiydc46PFnRf"
_TABLE_ID = "tblN5rGXczqUBk3p"


def report_phase_approved(
    project_id: str,
    phase_id: str,
    phase_name: str,
    judge_score: float | None,
    judge_passed: bool,
    duration_seconds: float | None,
    profile_id: str = "",
    comment: str = "",
) -> bool:
    """上报 Phase approve 事件到 bitable.

    失败静默返回 False，不抛异常。
    """
    try:
        from qualix.feishu.client import _get_user_email, bitable_create_record, is_logged_in

        if not is_logged_in():
            return False

        fields: dict[str, Any] = {
            "项目ID": project_id,
            "Phase": phase_id,
            "Phase名称": phase_name,
            "操作": "approve",
            "Judge评分": str(judge_score or 0),
            "是否通过": "是" if judge_passed else "否",
            "耗时(秒)": str(int(duration_seconds or 0)),
            "用户": _get_user_email(),
            "时间": time.strftime("%Y-%m-%d"),
            "Profile": profile_id,
        }
        record_id = bitable_create_record(_BASE_TOKEN, _TABLE_ID, fields)
        return record_id is not None
    except Exception:
        return False
