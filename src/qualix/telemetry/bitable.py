"""Qualix bitable telemetry module.

Opt-in only. Disabled by default.

Set QUALIX_TELEMETRY_ENABLED=1 and configure Feishu credentials to enable
sending anonymous phase-approval events to a shared team bitable table.

Privacy: when enabled, the following fields are sent: project_id, phase_id,
judge score, duration, date, and the Feishu email of the authenticated user.
No source code, PRD content, or phase reports are transmitted.
"""

from __future__ import annotations

import os
import time
from typing import Any

# Maintainer-controlled shared table. Requires opt-in to activate.
_BASE_TOKEN = "FQtabFSMTauogmstiydc46PFnRf"
_TABLE_ID = "tblN5rGXczqUBk3p"


def _is_telemetry_enabled() -> bool:
    """Return True only when the user has explicitly opted in."""
    return os.environ.get("QUALIX_TELEMETRY_ENABLED", "0").strip() == "1"


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
    """Report a Phase approve event to the shared bitable table.

    Only runs when QUALIX_TELEMETRY_ENABLED=1 AND Feishu credentials are
    configured. Fails silently and never blocks the main workflow.
    """
    if not _is_telemetry_enabled():
        return False

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
